import json
import uuid
import subprocess
import sys
import threading
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, Query, HTTPException
from src.database import get_db
from src.api.dependencies import require_internal_api_key
from src.models.schemas import (
    JobUpsertRequest,
    BatchUpsertRequest,
    BatchUpsertResponse,
    ScoreUpdate,
    SearchHistoryCreate,
    ScrapeRequest,
    ScrapeStatusResponse,
)

AVAILABLE_SCRAPERS = ["indeed", "linkedin", "arbeitsagentur", "stepstone", "xing"]
_scrape_tasks = {}  # task_id -> {status, scrapers, started_at, result}

router = APIRouter(prefix="/api/internal", dependencies=[Depends(require_internal_api_key)])


def _normalize_score(score: Optional[float]) -> Optional[float]:
    if score is None:
        return None
    if score <= 1.0:
        return score * 100
    return min(score, 100.0)


def _upsert_job(conn, job: JobUpsertRequest) -> tuple[dict, str]:
    """Returns (row, action) where action is 'inserted' or 'updated'."""
    normalized_score = _normalize_score(job.match_score)
    job_data = job.model_dump()
    job_data["match_score"] = normalized_score
    job_data_json = json.dumps(job_data)
    now = datetime.now(timezone.utc).isoformat()

    existing = conn.execute(
        "SELECT id, match_score FROM applications WHERE job_id = ?", (job.id,)
    ).fetchone()

    if existing:
        current_score = existing["match_score"] or 0
        new_score = normalized_score or 0
        if new_score >= current_score:
            conn.execute(
                """UPDATE applications
                   SET job_data = ?, match_score = ?, updated_at = ?
                   WHERE job_id = ?""",
                (job_data_json, normalized_score, now, job.id),
            )
        row = conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job.id,)
        ).fetchone()
        return row, "updated"
    else:
        app_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO applications
               (id, job_id, job_data, match_score, status, status_history, tags, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'wishlist', '[]', '[]', '', ?, ?)""",
            (app_id, job.id, job_data_json, normalized_score, now, now),
        )
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (app_id,)
        ).fetchone()
        return row, "inserted"


@router.post("/jobs")
def upsert_job(job: JobUpsertRequest):
    with get_db() as conn:
        row, action = _upsert_job(conn, job)
    return {**row, "_action": action}


@router.post("/jobs/batch", response_model=BatchUpsertResponse)
def batch_upsert_jobs(batch: BatchUpsertRequest):
    inserted = 0
    updated = 0
    errors = []

    with get_db() as conn:
        for i, job in enumerate(batch.jobs):
            try:
                _, action = _upsert_job(conn, job)
                if action == "inserted":
                    inserted += 1
                else:
                    updated += 1
            except Exception as e:
                errors.append(f"Job {i} ({job.id}): {str(e)}")

    return {"inserted": inserted, "updated": updated, "errors": errors}


@router.patch("/applications/{application_id}/score")
def update_score(application_id: str, update: ScoreUpdate):
    normalized = _normalize_score(update.match_score)
    details_json = json.dumps(update.match_details) if update.match_details else None
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
        if not existing:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Application not found")

        if details_json:
            conn.execute(
                "UPDATE applications SET match_score = ?, match_details = ?, updated_at = ? WHERE id = ?",
                (normalized, details_json, now, application_id),
            )
        else:
            conn.execute(
                "UPDATE applications SET match_score = ?, updated_at = ? WHERE id = ?",
                (normalized, now, application_id),
            )

        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()

    return row


@router.get("/jobs/unscored")
def list_unscored(limit: int = Query(20, ge=1, le=100)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM applications WHERE match_score IS NULL LIMIT ?", (limit,)
        ).fetchall()
    return rows


def _run_scrapers_background(task_id, scrapers, parallel=False, query=None, location=None):
    """Run scrapers in a background thread."""
    try:
        _scrape_tasks[task_id]["status"] = "running"
        scrapers_dir = Path(__file__).resolve().parents[3] / "scrapers"
        cmd = [sys.executable, str(scrapers_dir / "run_all.py")] + scrapers
        if parallel:
            cmd.append("--parallel")
        if query:
            cmd.extend(["--query", query])
        if location:
            cmd.extend(["--location", location])
        result = subprocess.run(
            cmd,
            cwd=str(scrapers_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
        _scrape_tasks[task_id]["status"] = "completed" if result.returncode == 0 else "failed"
        _scrape_tasks[task_id]["result"] = {
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-1000:] if result.stderr else "",
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        _scrape_tasks[task_id]["status"] = "timeout"
        _scrape_tasks[task_id]["result"] = {"error": "Scraping timed out after 600s"}
    except Exception as e:
        _scrape_tasks[task_id]["status"] = "failed"
        _scrape_tasks[task_id]["result"] = {"error": str(e)}


@router.post("/scrape", response_model=ScrapeStatusResponse)
def trigger_scrape(req: ScrapeRequest):
    scrapers = req.scrapers or AVAILABLE_SCRAPERS
    for s in scrapers:
        if s not in AVAILABLE_SCRAPERS:
            raise HTTPException(400, f"Unknown scraper: {s}. Available: {AVAILABLE_SCRAPERS}")

    running = [t for t in _scrape_tasks.values() if t["status"] == "running"]
    if running:
        raise HTTPException(409, "A scrape is already running")

    task_id = str(uuid.uuid4())[:8]
    _scrape_tasks[task_id] = {
        "status": "starting",
        "scrapers": scrapers,
        "query": req.query,
        "location": req.location,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
    }
    thread = threading.Thread(target=_run_scrapers_background, args=(task_id, scrapers, req.parallel, req.query, req.location), daemon=True)
    thread.start()

    return {"task_id": task_id, "status": "starting", "scrapers": scrapers}


@router.get("/scrape/{task_id}")
def get_scrape_status(task_id: str):
    if task_id not in _scrape_tasks:
        raise HTTPException(404, "Task not found")
    task = _scrape_tasks[task_id]
    return {
        "task_id": task_id,
        "status": task["status"],
        "scrapers": task["scrapers"],
        "started_at": task["started_at"],
        "result": task["result"],
    }


@router.get("/scrape")
def list_scrape_tasks():
    return {
        "available_scrapers": AVAILABLE_SCRAPERS,
        "tasks": {k: {"status": v["status"], "scrapers": v["scrapers"], "started_at": v["started_at"]} for k, v in _scrape_tasks.items()},
    }


public_router = APIRouter(prefix="/api")


@public_router.post("/scrape")
def public_trigger_scrape(req: ScrapeRequest):
    scrapers = req.scrapers or ["linkedin", "stepstone", "xing", "arbeitsagentur"]
    for s in scrapers:
        if s not in AVAILABLE_SCRAPERS:
            raise HTTPException(400, f"Unknown scraper: {s}. Available: {AVAILABLE_SCRAPERS}")

    running = [t for t in _scrape_tasks.values() if t["status"] == "running"]
    if running:
        raise HTTPException(409, "A scrape is already running")

    task_id = str(uuid.uuid4())[:8]
    _scrape_tasks[task_id] = {
        "status": "starting",
        "scrapers": scrapers,
        "query": req.query,
        "location": req.location,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
    }
    thread = threading.Thread(
        target=_run_scrapers_background,
        args=(task_id, scrapers, req.parallel, req.query, req.location),
        daemon=True,
    )
    thread.start()

    return {"task_id": task_id, "status": "starting", "scrapers": scrapers}


@public_router.get("/scrape/{task_id}")
def public_get_scrape_status(task_id: str):
    if task_id not in _scrape_tasks:
        raise HTTPException(404, "Task not found")
    task = _scrape_tasks[task_id]
    return {
        "task_id": task_id,
        "status": task["status"],
        "scrapers": task["scrapers"],
        "query": task.get("query"),
        "location": task.get("location"),
        "started_at": task["started_at"],
        "result": task["result"],
    }


@public_router.get("/scrape")
def public_list_scrapes():
    return {
        "available_scrapers": AVAILABLE_SCRAPERS,
        "tasks": {
            k: {
                "status": v["status"],
                "scrapers": v["scrapers"],
                "query": v.get("query"),
                "location": v.get("location"),
                "started_at": v["started_at"],
            }
            for k, v in _scrape_tasks.items()
        },
    }


@public_router.get("/search-history")
def public_search_history(limit: int = Query(20, ge=1, le=100)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM search_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return rows


@router.post("/search-history")
def log_search(entry: SearchHistoryCreate):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO search_history
               (query, location, sources_used, results_count, new_jobs_count, execution_time_seconds)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                entry.query,
                entry.location,
                json.dumps(entry.sources_used) if entry.sources_used else None,
                entry.results_count,
                entry.new_jobs_count,
                entry.execution_time_seconds,
            ),
        )
        row_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        row = conn.execute("SELECT * FROM search_history WHERE id = ?", (row_id,)).fetchone()
    return row
