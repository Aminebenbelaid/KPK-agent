"""Generation & apply: cover letters, market reports, and the Apply Assistant."""
import os
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from src.database import get_db
from src.api.routes.profile import load_profile
from src.api.routes.settings import get_session_setting
from src.matching import coverletter, report as report_mod, cvgen, llm
from src import task_queue

router = APIRouter(prefix="/api")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _best_app(conn, sid: str, job_id: str):
    return conn.execute(
        """WITH best AS (
               SELECT *, ROW_NUMBER() OVER (
                   PARTITION BY job_id ORDER BY match_score DESC, updated_at DESC
               ) rn FROM applications WHERE session_id = ? AND job_id = ?
           )
           SELECT * FROM best WHERE rn = 1""",
        (sid, job_id),
    ).fetchone()


def _all_experiences(conn, sid: str):
    return conn.execute(
        "SELECT kind, title, organization, description, ai_summary, stack "
        "FROM experiences WHERE session_id = ?",
        (sid,),
    ).fetchall()


# ── Market trend report ──

@router.get("/report")
def market_report(request: Request, q: str = Query(None)):
    sid = request.state.effective_sid
    with get_db() as conn:
        rows = conn.execute(
            """WITH best AS (
                   SELECT *, ROW_NUMBER() OVER (
                       PARTITION BY job_id ORDER BY match_score DESC, updated_at DESC
                   ) rn FROM applications WHERE session_id = ?
               )
               SELECT job_data FROM best WHERE rn = 1""",
            (sid,),
        ).fetchall()
    jobs = []
    for r in rows:
        data = r.get("job_data") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                continue
        if q:
            hay = f"{data.get('title','')} {data.get('company','')}".lower()
            if q.lower() not in hay:
                continue
        jobs.append(data)
    return report_mod.build_report(jobs, query=q)


# ── Cover letter (queued) ──

def _make_letter(sid: str, job_id: str) -> dict:
    with get_db() as conn:
        app_row = _best_app(conn, sid, job_id)
        if not app_row:
            raise RuntimeError("Job not found")
        experiences = _all_experiences(conn, sid)
    job = app_row.get("job_data") or {}
    result = coverletter.generate(
        job, app_row["id"], experiences, load_profile(sid), sid=sid,
        instructions=get_session_setting(sid, "cover_letter_instructions"),
    )
    if not result.get("text"):
        raise RuntimeError("Cover letter generation failed. Try again.")
    with get_db() as conn:
        conn.execute(
            "UPDATE applications SET cover_letter_path = ?, updated_at = ? WHERE id = ?",
            (result["pdf"], _now(), app_row["id"]),
        )
    return {
        "app_id": app_row["id"],
        "text": result["text"],
        "compiled": result["compiled"],
        "download": f"/api/applications/{app_row['id']}/cover-letter" if result["compiled"] else None,
    }


@router.post("/cover-letter/{job_id}")
def make_cover_letter(request: Request, job_id: str):
    if not llm.is_configured():
        raise HTTPException(400, "LLM is not configured on the server.")
    sid = request.state.effective_sid
    return task_queue.submit("cover-letter", lambda: _make_letter(sid, job_id), sid=sid)


@router.get("/applications/{app_id}/cover-letter")
def download_cover_letter(request: Request, app_id: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT cover_letter_path FROM applications WHERE id = ? AND session_id = ?",
            (app_id, request.state.effective_sid),
        ).fetchone()
    if not row or not row.get("cover_letter_path") or not os.path.exists(row["cover_letter_path"]):
        raise HTTPException(404, "No cover letter generated yet")
    return FileResponse(row["cover_letter_path"], media_type="application/pdf", filename="cover_letter.pdf")


# ── Apply Assistant (queued: CV + letter in one task) ──

APPLY_CHECKLIST = [
    "Review the tailored CV and cover letter",
    "Open the original posting and start the application",
    "Paste / upload the CV and cover letter",
    "Double-check name, contact details and any custom questions",
    "Submit, then mark this job as Applied",
]


def _make_kit(sid: str, job_id: str) -> dict:
    with get_db() as conn:
        app_row = _best_app(conn, sid, job_id)
        if not app_row:
            raise RuntimeError("Job not found")
        experiences = _all_experiences(conn, sid)
    job = app_row.get("job_data") or {}
    profile = load_profile(sid)
    app_id = app_row["id"]

    cv_result = cvgen.generate_for_job(
        job, app_id, experiences, sid=sid,
        instructions=get_session_setting(sid, "cv_instructions"),
        profile=profile,
    )
    letter = coverletter.generate(
        job, app_id, experiences, profile, sid=sid,
        instructions=get_session_setting(sid, "cover_letter_instructions"),
    )

    sets, params = [], []
    if cv_result.get("compiled"):
        sets.append("cv_path = ?"); params.append(cv_result["pdf"])
    if letter.get("compiled"):
        sets.append("cover_letter_path = ?"); params.append(letter["pdf"])
    if sets:
        sets.append("updated_at = ?"); params.append(_now()); params.append(app_id)
        with get_db() as conn:
            conn.execute(f"UPDATE applications SET {', '.join(sets)} WHERE id = ?", params)

    return {
        "app_id": app_id,
        "apply_url": job.get("url") or "",
        "cv_download": f"/api/applications/{app_id}/cv" if cv_result.get("compiled") else None,
        "cover_letter_download": f"/api/applications/{app_id}/cover-letter" if letter.get("compiled") else None,
        "cover_letter_text": letter.get("text"),
        "checklist": APPLY_CHECKLIST,
    }


@router.post("/apply-kit/{job_id}")
def apply_kit(request: Request, job_id: str):
    if not llm.is_configured():
        raise HTTPException(400, "LLM is not configured on the server.")
    sid = request.state.effective_sid
    return task_queue.submit("apply-kit", lambda: _make_kit(sid, job_id), sid=sid)
