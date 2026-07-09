import os
import json
import uuid
import subprocess
import sys
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, Query, HTTPException, Header, Request
from src.database import get_db
from src.api.dependencies import require_internal_api_key
from src.models.schemas import (
    JobUpsertRequest,
    BatchUpsertRequest,
    BatchUpsertResponse,
    SearchHistoryCreate,
    ScrapeRequest,
)
from src.matching.skills import extract_skills, normalize_skills
from src.matching.dedup import find_duplicate
from src import task_queue
from src.sessions import OWNER_SID

AVAILABLE_SCRAPERS = ["linkedin", "arbeitsagentur", "stepstone", "xing"]
MAX_JOBS_PER_SESSION = 400

_scrape_tasks = {}  # task_id -> {status, scrapers, sid, queue_id, started_at, result}

router = APIRouter(prefix="/api/internal", dependencies=[Depends(require_internal_api_key)])


def _normalize_score(score: Optional[float]) -> Optional[float]:
    if score is None:
        return None
    if score <= 1.0:
        return score * 100
    return min(score, 100.0)


def _enrich_skills(job_data: dict) -> dict:
    """Extract skills from title+description and merge with any provided skills."""
    extracted = extract_skills(
        job_data.get("title", ""),
        job_data.get("description_clean") or job_data.get("description_raw") or "",
    )
    provided = list(job_data.get("skills_required") or [])
    job_data["skills_required"] = normalize_skills(provided + extracted)
    if job_data.get("technologies"):
        job_data["technologies"] = normalize_skills(job_data["technologies"])
    return job_data


def _merge_duplicate(conn, canonical: dict, job_data: dict, now: str) -> dict:
    """Record an extra source on the canonical row instead of inserting a new one."""
    data = canonical["job_data"]
    also_on = data.get("also_on") or []
    entry = {"source": job_data.get("source"), "url": job_data.get("url")}
    if entry["source"] and entry["source"] not in [a.get("source") for a in also_on] \
            and entry["source"] != data.get("source"):
        also_on.append(entry)
    data["also_on"] = also_on
    conn.execute(
        "UPDATE applications SET job_data = ?, updated_at = ? WHERE id = ?",
        (json.dumps(data), now, canonical["id"]),
    )
    return conn.execute(
        "SELECT * FROM applications WHERE id = ?", (canonical["id"],)
    ).fetchone()


def _upsert_job(conn, job: JobUpsertRequest, sid: str, dedup: bool = True) -> tuple[dict, str]:
    """Returns (row, action): 'inserted', 'updated', 'merged' or 'skipped' (cap)."""
    normalized_score = _normalize_score(job.match_score)
    job_data = _enrich_skills(job.model_dump())
    job_data["match_score"] = normalized_score
    job_data_json = json.dumps(job_data)
    now = datetime.now(timezone.utc).isoformat()

    existing = conn.execute(
        "SELECT id, match_score, job_data FROM applications WHERE session_id = ? AND job_id = ?",
        (sid, job.id),
    ).fetchone()

    if existing:
        # Always refresh the scraped content (e.g. newly-fetched descriptions),
        # but never downgrade an existing match score.
        current_score = existing["match_score"]
        if current_score is not None and (normalized_score is None or current_score >= normalized_score):
            keep_score = current_score
        else:
            keep_score = normalized_score

        prev = existing["job_data"]
        if isinstance(prev, str):
            try:
                prev = json.loads(prev)
            except (ValueError, TypeError):
                prev = {}
        if isinstance(prev, dict) and prev.get("also_on") and not job_data.get("also_on"):
            job_data["also_on"] = prev["also_on"]

        job_data["match_score"] = keep_score
        conn.execute(
            """UPDATE applications
               SET job_data = ?, match_score = ?, updated_at = ?
               WHERE session_id = ? AND job_id = ?""",
            (json.dumps(job_data), keep_score, now, sid, job.id),
        )
        row = conn.execute(
            "SELECT * FROM applications WHERE session_id = ? AND job_id = ?", (sid, job.id)
        ).fetchone()
        return row, "updated"

    # New job_id for this session: dedup against its own rows, then respect the cap.
    if dedup:
        canonical = find_duplicate(conn, job_data, sid)
        if canonical:
            row = _merge_duplicate(conn, canonical, job_data, now)
            return row, "merged"

    count = conn.execute(
        "SELECT COUNT(*) c FROM applications WHERE session_id = ?", (sid,)
    ).fetchone()["c"]
    if count >= MAX_JOBS_PER_SESSION:
        return {}, "skipped"

    app_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO applications
           (id, job_id, job_data, match_score, status, status_history, tags, notes, session_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'wishlist', '[]', '[]', '', ?, ?, ?)""",
        (app_id, job.id, job_data_json, normalized_score, sid, now, now),
    )
    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (app_id,)
    ).fetchone()
    return row, "inserted"


def _sid_from_header(x_kpk_session: Optional[str]) -> str:
    return (x_kpk_session or "").strip() or OWNER_SID


@router.post("/jobs/batch", response_model=BatchUpsertResponse)
def batch_upsert_jobs(batch: BatchUpsertRequest, x_kpk_session: Optional[str] = Header(None)):
    sid = _sid_from_header(x_kpk_session)
    inserted = 0
    updated = 0
    errors = []

    with get_db() as conn:
        for i, job in enumerate(batch.jobs):
            try:
                _, action = _upsert_job(conn, job, sid)
                if action == "inserted":
                    inserted += 1
                elif action == "skipped":
                    errors.append(f"Job {job.id}: session job limit reached")
                else:
                    updated += 1
            except Exception as e:
                errors.append(f"Job {i} ({job.id}): {str(e)}")

    return {"inserted": inserted, "updated": updated, "errors": errors}


@router.post("/search-history")
def log_search(entry: SearchHistoryCreate, x_kpk_session: Optional[str] = Header(None)):
    sid = _sid_from_header(x_kpk_session)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO search_history
               (query, location, sources_used, results_count, new_jobs_count, execution_time_seconds, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.query,
                entry.location,
                json.dumps(entry.sources_used) if entry.sources_used else None,
                entry.results_count,
                entry.new_jobs_count,
                entry.execution_time_seconds,
                sid,
            ),
        )
    return {"logged": True}


# ── Scraping (public, session-scoped, executed via the global queue) ──

def _run_scrape(task_id: str, sid: str, scrapers: list, parallel: bool, query, location):
    task = _scrape_tasks[task_id]
    task["status"] = "running"
    try:
        scrapers_dir = Path(__file__).resolve().parents[3] / "scrapers"
        cmd = [sys.executable, str(scrapers_dir / "run_all.py")] + scrapers
        if parallel:
            cmd.append("--parallel")
        if query:
            cmd.extend(["--query", query])
        if location:
            cmd.extend(["--location", location])
        env = dict(os.environ)
        env["KPK_SESSION"] = sid
        result = subprocess.run(
            cmd, cwd=str(scrapers_dir), capture_output=True, text=True,
            timeout=600, env=env,
        )
        task["status"] = "completed" if result.returncode == 0 else "failed"
        task["result"] = {
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-1000:] if result.stderr else "",
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        task["status"] = "timeout"
        task["result"] = {"error": "Scraping timed out after 600s"}
    except Exception as e:  # noqa: BLE001 - surfaced to the poller
        task["status"] = "failed"
        task["result"] = {"error": str(e)}


public_router = APIRouter(prefix="/api")


@public_router.post("/scrape")
def public_trigger_scrape(request: Request, req: ScrapeRequest):
    sid = request.state.effective_sid
    scrapers = req.scrapers or AVAILABLE_SCRAPERS
    for s in scrapers:
        if s not in AVAILABLE_SCRAPERS:
            raise HTTPException(400, f"Unknown scraper: {s}. Available: {AVAILABLE_SCRAPERS}")

    # one pending scrape per session is enough
    for t in _scrape_tasks.values():
        if t["sid"] == sid and t["status"] in ("queued", "running"):
            raise HTTPException(409, "You already have a scrape queued or running")

    task_id = str(uuid.uuid4())[:8]
    _scrape_tasks[task_id] = {
        "status": "queued",
        "sid": sid,
        "scrapers": scrapers,
        "query": req.query,
        "location": req.location,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
        "queue_id": None,
    }
    sub = task_queue.submit(
        "scrape",
        lambda: _run_scrape(task_id, sid, scrapers, req.parallel, req.query, req.location),
        sid=sid,
    )
    _scrape_tasks[task_id]["queue_id"] = sub["task_id"]
    return {"task_id": task_id, "status": "queued", "position": sub["position"], "scrapers": scrapers}


@public_router.get("/scrape/{task_id}")
def public_get_scrape_status(request: Request, task_id: str):
    task = _scrape_tasks.get(task_id)
    if not task or task["sid"] != request.state.effective_sid:
        raise HTTPException(404, "Task not found")
    position = task_queue.position(task["queue_id"]) if task["queue_id"] else 0
    return {
        "task_id": task_id,
        "status": task["status"],
        "position": position,
        "scrapers": task["scrapers"],
        "query": task.get("query"),
        "location": task.get("location"),
        "started_at": task["started_at"],
        "result": task["result"],
    }


@public_router.get("/scrape")
def public_list_scrapes(request: Request):
    sid = request.state.effective_sid
    return {
        "available_scrapers": AVAILABLE_SCRAPERS,
        "queue": task_queue.queue_overview(),
        "tasks": {
            k: {"status": v["status"], "scrapers": v["scrapers"],
                "query": v.get("query"), "location": v.get("location"),
                "started_at": v["started_at"]}
            for k, v in _scrape_tasks.items() if v["sid"] == sid
        },
    }


@public_router.get("/search-history")
def public_search_history(request: Request, limit: int = Query(20, ge=1, le=100)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM search_history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (request.state.effective_sid, limit),
        ).fetchall()
    return rows
