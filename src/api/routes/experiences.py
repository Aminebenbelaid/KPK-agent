"""Experience base: CV upload/parse, experience CRUD, per-job matching, CV gen.

All heavy LLM work (parsing, tailoring, matching) is executed through the global
work queue; endpoints return a queue task id that the client polls.
"""
import os
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse

from src.database import get_db
from src.models.schemas import (
    ExperienceCreate,
    ExperienceUpdate,
    CVParseRequest,
    CVConfirmRequest,
)
from src.matching import cv, llm, cvgen
from src.api.routes.profile import load_profile
from src.api.routes.settings import get_session_setting
from src import task_queue

router = APIRouter(prefix="/api")

MAX_EXPERIENCES = 60
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sid(request: Request) -> str:
    return request.state.effective_sid


def _insert_experience(conn, sid: str, data: dict) -> dict:
    exp_id = str(uuid.uuid4())
    now = _now()
    conn.execute(
        """INSERT INTO experiences
           (id, kind, title, organization, description, stack, start_date, end_date,
            ai_summary, ai_tags, source, sort_order, session_id, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            exp_id,
            data.get("kind", "job"),
            data.get("title", "Untitled"),
            data.get("organization", "") or "",
            data.get("description", "") or "",
            json.dumps(data.get("stack") or []),
            data.get("start_date"),
            data.get("end_date"),
            data.get("ai_summary", "") or "",
            json.dumps(data.get("ai_tags") or []),
            data.get("source", "manual"),
            data.get("sort_order", 0),
            sid,
            now,
            now,
        ),
    )
    return conn.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,)).fetchone()


def _count_experiences(conn, sid: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) c FROM experiences WHERE session_id = ?", (sid,)
    ).fetchone()["c"]


def _best_app_by_job(conn, sid: str, job_id: str):
    return conn.execute(
        """WITH best AS (
               SELECT *, ROW_NUMBER() OVER (
                   PARTITION BY job_id ORDER BY match_score DESC, updated_at DESC
               ) rn FROM applications WHERE session_id = ? AND job_id = ?
           )
           SELECT * FROM best WHERE rn = 1""",
        (sid, job_id),
    ).fetchone()


# ── CRUD ──

@router.get("/experiences")
def list_experiences(request: Request):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM experiences WHERE session_id = ? ORDER BY sort_order ASC, created_at DESC",
            (_sid(request),),
        ).fetchall()
    return rows


@router.post("/experiences")
def create_experience(request: Request, exp: ExperienceCreate):
    sid = _sid(request)
    data = exp.model_dump()
    if exp.source != "cv" and not exp.ai_summary and llm.is_configured_for(sid):
        with llm.for_session(sid):
            enriched = cv.enrich_experience(
                exp.title, exp.description or "", exp.stack, exp.organization or ""
            )
        if enriched:
            data["ai_summary"] = enriched["ai_summary"]
            data["ai_tags"] = enriched["ai_tags"]
            data["stack"] = enriched["stack"]
    with get_db() as conn:
        if _count_experiences(conn, sid) >= MAX_EXPERIENCES:
            raise HTTPException(400, f"Experience limit reached ({MAX_EXPERIENCES})")
        row = _insert_experience(conn, sid, data)
    return row


@router.put("/experiences/{exp_id}")
def update_experience(request: Request, exp_id: str, update: ExperienceUpdate):
    sid = _sid(request)
    patch = {k: v for k, v in update.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "No fields to update")

    sets, params = [], []
    for key, val in patch.items():
        if key in ("stack", "ai_tags"):
            val = json.dumps(val)
        sets.append(f"{key} = ?")
        params.append(val)
    sets.append("updated_at = ?")
    params.append(_now())
    params.extend([exp_id, sid])

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM experiences WHERE id = ? AND session_id = ?", (exp_id, sid)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Experience not found")
        conn.execute(
            f"UPDATE experiences SET {', '.join(sets)} WHERE id = ? AND session_id = ?", params
        )
        row = conn.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,)).fetchone()
    return row


@router.delete("/experiences/{exp_id}")
def delete_experience(request: Request, exp_id: str):
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM experiences WHERE id = ? AND session_id = ?",
            (exp_id, _sid(request)),
        )
        if not cur.rowcount:
            raise HTTPException(404, "Experience not found")
    return {"deleted": exp_id}


# ── CV parse / confirm (parsing runs on the queue) ──

def _parse_job_fn(sid: str, text: str, extra: dict):
    def run():
        with llm.for_session(sid):
            return {"experiences": cv.parse_cv(text), "text_chars": len(text), **extra}
    return run


@router.post("/cv/parse-text")
def parse_cv_text(request: Request, req: CVParseRequest):
    sid = _sid(request)
    if not llm.is_configured_for(sid):
        raise HTTPException(400, llm.NEEDS_KEY_MSG)
    return task_queue.submit("cv-parse", _parse_job_fn(sid, req.text, {}), sid=sid)


@router.post("/cv/parse-file")
async def parse_cv_file(request: Request, file: UploadFile = File(...)):
    sid = _sid(request)
    if not llm.is_configured_for(sid):
        raise HTTPException(400, llm.NEEDS_KEY_MSG)
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 8 MB)")
    name = (file.filename or "").lower()
    if name.endswith(".pdf"):
        text = cv.extract_pdf_text(raw)
        if not text:
            raise HTTPException(422, "Could not extract text from this PDF.")
    else:
        text = raw.decode("utf-8", errors="ignore")
    return task_queue.submit(
        "cv-parse", _parse_job_fn(sid, text, {"filename": file.filename}), sid=sid
    )


@router.post("/cv/confirm")
def confirm_cv(request: Request, req: CVConfirmRequest):
    sid = _sid(request)
    saved = []
    with get_db() as conn:
        if req.replace_existing:
            conn.execute(
                "DELETE FROM experiences WHERE source = 'cv' AND session_id = ?", (sid,)
            )
        for i, exp in enumerate(req.experiences):
            if _count_experiences(conn, sid) >= MAX_EXPERIENCES:
                break
            data = exp.model_dump()
            data["source"] = "cv"
            data["sort_order"] = i
            saved.append(_insert_experience(conn, sid, data))
    return {"saved": len(saved), "experiences": saved}


# ── Per-job experience matching (queued) ──

def _match_experiences_job(sid: str, job_id: str) -> dict:
    with get_db() as conn:
        app_row = _best_app_by_job(conn, sid, job_id)
        if not app_row:
            raise RuntimeError("Job not found")
        experiences = conn.execute(
            "SELECT * FROM experiences WHERE session_id = ?", (sid,)
        ).fetchall()

    job = app_row.get("job_data") or {}
    with llm.for_session(sid):
        result = cv.match_experiences_to_job(job, experiences)
    if result is None:
        raise RuntimeError("LLM matching failed. Try again.")

    by_id = {e["id"]: e for e in experiences}
    for m in result["matches"]:
        exp = by_id.get(m["id"])
        if exp:
            m["title"] = exp.get("title")
            m["kind"] = exp.get("kind")
            m["organization"] = exp.get("organization")

    with get_db() as conn:
        details = app_row.get("match_details") or {}
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except (ValueError, TypeError):
                details = {}
        details["experience_match"] = {**result, "matched_at": _now()}
        conn.execute(
            "UPDATE applications SET match_details = ?, updated_at = ? WHERE id = ?",
            (json.dumps(details), _now(), app_row["id"]),
        )
    return result


@router.post("/match/experiences/{job_id}")
def match_experiences(request: Request, job_id: str):
    sid = _sid(request)
    if not llm.is_configured_for(sid):
        raise HTTPException(400, llm.NEEDS_KEY_MSG)
    return task_queue.submit("exp-match", lambda: _match_experiences_job(sid, job_id), sid=sid)


# ── CV template (per session) ──

@router.get("/cv/template")
def get_cv_template(request: Request):
    sid = _sid(request)
    try:
        return {"tex": cvgen.load_template(sid), "is_override": cvgen.override_template(sid).exists()}
    except FileNotFoundError:
        raise HTTPException(404, "No CV template found")


@router.put("/cv/template")
def put_cv_template(request: Request, req: CVParseRequest):
    sid = _sid(request)
    if len(req.text) > 200_000:
        raise HTTPException(413, "Template too large")
    path = cvgen.override_template(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(req.text, encoding="utf-8")
    return {"saved": True, "chars": len(req.text)}


# ── CV photo (per session) ──

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


@router.post("/cv/photo")
async def upload_cv_photo(request: Request, file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "Photo too large (max 5 MB)")
    if raw.startswith(_PNG_MAGIC):
        pass  # png saved as-is
    elif raw.startswith(_JPEG_MAGIC):
        # convert jpeg -> png so the template's pdp.png reference works
        try:
            from PIL import Image  # noqa: F401 - optional
            import io
            img = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            raw = buf.getvalue()
        except ImportError:
            raise HTTPException(415, "Please upload a PNG image")
    else:
        raise HTTPException(415, "Unsupported image type (use PNG or JPEG)")

    path = cvgen.photo_path(_sid(request))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"saved": True, "bytes": len(raw)}


@router.get("/cv/photo")
def get_cv_photo(request: Request):
    path = cvgen.photo_path(_sid(request))
    if not path.exists():
        raise HTTPException(404, "No photo uploaded")
    return FileResponse(str(path), media_type="image/png")


@router.delete("/cv/photo")
def delete_cv_photo(request: Request):
    path = cvgen.photo_path(_sid(request))
    if path.exists():
        path.unlink()
    return {"deleted": True}


# ── Tailored CV generation (queued) ──

def _tailor_job(sid: str, job_id: str) -> dict:
    with get_db() as conn:
        app_row = _best_app_by_job(conn, sid, job_id)
        if not app_row:
            raise RuntimeError("Job not found")
        experiences = conn.execute(
            "SELECT kind, title, organization, description, ai_summary, stack "
            "FROM experiences WHERE session_id = ?",
            (sid,),
        ).fetchall()

    job = app_row.get("job_data") or {}
    with llm.for_session(sid):
        result = cvgen.generate_for_job(
            job, app_row["id"], experiences, sid=sid,
            instructions=get_session_setting(sid, "cv_instructions"),
            profile=load_profile(sid),
        )
    if not result["compiled"]:
        raise RuntimeError(f"CV compile failed: {result.get('log', '')[:400]}")

    with get_db() as conn:
        conn.execute(
            "UPDATE applications SET cv_path = ?, cv_variant = ?, updated_at = ? WHERE id = ?",
            (result["pdf"], (job.get("title") or "tailored")[:80], _now(), app_row["id"]),
        )

    return {
        "app_id": app_row["id"],
        "tailored": result["tailored"],
        "emphasized": result["emphasized"],
        "download": f"/api/applications/{app_row['id']}/cv",
    }


@router.post("/cv/tailor/{job_id}")
def tailor_cv(request: Request, job_id: str):
    sid = _sid(request)
    if not llm.is_configured_for(sid):
        raise HTTPException(400, llm.NEEDS_KEY_MSG)
    return task_queue.submit("cv-tailor", lambda: _tailor_job(sid, job_id), sid=sid)


@router.get("/applications/{app_id}/cv")
def download_cv(request: Request, app_id: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT cv_path FROM applications WHERE id = ? AND session_id = ?",
            (app_id, _sid(request)),
        ).fetchone()
    if not row or not row.get("cv_path") or not os.path.exists(row["cv_path"]):
        raise HTTPException(404, "No CV generated for this job yet")
    return FileResponse(row["cv_path"], media_type="application/pdf", filename="cv.pdf")
