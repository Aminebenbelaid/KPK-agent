"""Experience base: CV upload/parse, manual experience CRUD, per-job matching, CV gen."""
import os
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from src.database import get_db
from src.models.schemas import (
    ExperienceCreate,
    ExperienceUpdate,
    CVParseRequest,
    CVConfirmRequest,
)
from src.matching import cv, llm, cvgen

router = APIRouter(prefix="/api")


def _best_app_by_job(conn, job_id: str):
    return conn.execute(
        """WITH best AS (
               SELECT *, ROW_NUMBER() OVER (
                   PARTITION BY job_id ORDER BY match_score DESC, updated_at DESC
               ) rn FROM applications WHERE job_id = ?
           )
           SELECT * FROM best WHERE rn = 1""",
        (job_id,),
    ).fetchone()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_exp(row) -> dict:
    return row  # get_db already parses stack/ai_tags JSON


def _insert_experience(conn, data: dict) -> dict:
    exp_id = str(uuid.uuid4())
    now = _now()
    conn.execute(
        """INSERT INTO experiences
           (id, kind, title, organization, description, stack, start_date, end_date,
            ai_summary, ai_tags, source, sort_order, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            now,
            now,
        ),
    )
    return conn.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,)).fetchone()


# ── CRUD ──

@router.get("/experiences")
def list_experiences():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM experiences ORDER BY sort_order ASC, created_at DESC"
        ).fetchall()
    return rows


@router.post("/experiences")
def create_experience(exp: ExperienceCreate):
    data = exp.model_dump()
    # AI enrichment for manual entries that lack a summary.
    if exp.source != "cv" and not exp.ai_summary and llm.is_configured():
        enriched = cv.enrich_experience(
            exp.title, exp.description or "", exp.stack, exp.organization or ""
        )
        if enriched:
            data["ai_summary"] = enriched["ai_summary"]
            data["ai_tags"] = enriched["ai_tags"]
            data["stack"] = enriched["stack"]
    with get_db() as conn:
        row = _insert_experience(conn, data)
    return row


@router.put("/experiences/{exp_id}")
def update_experience(exp_id: str, update: ExperienceUpdate):
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
    params.append(exp_id)

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM experiences WHERE id = ?", (exp_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Experience not found")
        conn.execute(f"UPDATE experiences SET {', '.join(sets)} WHERE id = ?", params)
        row = conn.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,)).fetchone()
    return row


@router.delete("/experiences/{exp_id}")
def delete_experience(exp_id: str):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM experiences WHERE id = ?", (exp_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Experience not found")
        conn.execute("DELETE FROM experiences WHERE id = ?", (exp_id,))
    return {"deleted": exp_id}


# ── CV parse / confirm ──

@router.post("/cv/parse-text")
def parse_cv_text(req: CVParseRequest):
    if not llm.is_configured():
        raise HTTPException(400, "LLM is not configured. Add a Kisski API key in Settings.")
    experiences = cv.parse_cv(req.text)
    return {"experiences": experiences, "text_chars": len(req.text)}


@router.post("/cv/parse-file")
async def parse_cv_file(file: UploadFile = File(...)):
    if not llm.is_configured():
        raise HTTPException(400, "LLM is not configured. Add a Kisski API key in Settings.")
    raw = await file.read()
    name = (file.filename or "").lower()
    if name.endswith(".pdf"):
        text = cv.extract_pdf_text(raw)
        if not text:
            raise HTTPException(422, "Could not extract text from this PDF.")
    else:
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            raise HTTPException(422, "Could not read this file as text.")
    experiences = cv.parse_cv(text)
    return {"experiences": experiences, "text_chars": len(text), "filename": file.filename}


@router.post("/cv/confirm")
def confirm_cv(req: CVConfirmRequest):
    saved = []
    with get_db() as conn:
        if req.replace_existing:
            conn.execute("DELETE FROM experiences WHERE source = 'cv'")
        for i, exp in enumerate(req.experiences):
            data = exp.model_dump()
            data["source"] = "cv"
            data["sort_order"] = i
            saved.append(_insert_experience(conn, data))
    return {"saved": len(saved), "experiences": saved}


# ── Per-job experience matching (separate view) ──

@router.post("/match/experiences/{job_id}")
def match_experiences(job_id: str):
    if not llm.is_configured():
        raise HTTPException(400, "LLM is not configured. Add a Kisski API key in Settings.")

    with get_db() as conn:
        app_row = conn.execute(
            """WITH best AS (
                   SELECT *, ROW_NUMBER() OVER (
                       PARTITION BY job_id ORDER BY match_score DESC, updated_at DESC
                   ) rn FROM applications WHERE job_id = ?
               )
               SELECT * FROM best WHERE rn = 1""",
            (job_id,),
        ).fetchone()
        if not app_row:
            raise HTTPException(404, "Job not found")
        experiences = conn.execute("SELECT * FROM experiences").fetchall()

    job = app_row.get("job_data") or {}
    result = cv.match_experiences_to_job(job, experiences)
    if result is None:
        raise HTTPException(502, "LLM matching failed. Try again.")

    # Attach experience titles to each match for display, and cache in match_details.
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


# ── Tailored CV generation ──

@router.get("/cv/template")
def get_cv_template():
    try:
        return {"tex": cvgen.load_template(), "is_override": cvgen.override_template().exists()}
    except FileNotFoundError:
        raise HTTPException(404, "No CV template found")


@router.put("/cv/template")
def put_cv_template(req: CVParseRequest):
    """Save a CV template override (LaTeX) into the data volume."""
    path = cvgen.override_template()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(req.text, encoding="utf-8")
    return {"saved": True, "chars": len(req.text)}


@router.post("/cv/tailor/{job_id}")
def tailor_cv(job_id: str):
    if not llm.is_configured():
        raise HTTPException(400, "LLM is not configured. Add a Kisski API key in Settings.")
    with get_db() as conn:
        app_row = _best_app_by_job(conn, job_id)
        if not app_row:
            raise HTTPException(404, "Job not found")
        experiences = conn.execute(
            "SELECT kind, title, organization, description, ai_summary, stack FROM experiences"
        ).fetchall()

    job = app_row.get("job_data") or {}
    try:
        result = cvgen.generate_for_job(job, app_row["id"], experiences)
    except FileNotFoundError:
        raise HTTPException(400, "No CV template found. Import or paste one first.")

    if not result["compiled"]:
        raise HTTPException(502, f"CV compile failed: {result.get('log', '')[:500]}")

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


@router.get("/applications/{app_id}/cv")
def download_cv(app_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT cv_path FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not row or not row.get("cv_path") or not os.path.exists(row["cv_path"]):
        raise HTTPException(404, "No CV generated for this job yet")
    return FileResponse(row["cv_path"], media_type="application/pdf", filename="cv.pdf")
