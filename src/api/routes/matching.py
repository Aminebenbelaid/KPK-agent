"""Job-to-profile scoring endpoints (hybrid rule-based + optional LLM)."""
import json
import time
import uuid
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from src.database import get_db
from src.api.routes.profile import load_profile
from src.models.schemas import ScoreRunRequest
from src.matching import scorer, llm

router = APIRouter(prefix="/api")

# Only the best rule-scored candidates get the (rate-limited) LLM refinement pass.
LLM_TOP_N = 30

_score_tasks: dict[str, dict] = {}


def _parse_job(row) -> dict:
    data = row["job_data"]
    if isinstance(data, str):
        try:
            return json.loads(data)
        except (ValueError, TypeError):
            return {}
    return data or {}


def _augment_profile(profile: dict) -> dict:
    """Derive the candidate's skills and experience context from the Experience base.

    Skills come entirely from what the candidate has actually done (experience
    stacks + AI tags) rather than a manually-typed list. The profile provides only
    preferences (location, remote, salary, target roles, seniority). We also attach
    a brief ``experiences`` list so the LLM scorer can reason about real projects.
    """
    augmented = dict(profile or {})
    skills = []
    exps = []
    with get_db() as conn:
        rows = conn.execute(
            "SELECT kind, title, organization, stack, ai_summary, ai_tags FROM experiences"
        ).fetchall()
    for row in rows:
        for item in (row.get("stack") or []):
            skills.append(item)
        for tag in (row.get("ai_tags") or []):
            skills.append(tag)
        exps.append({
            "kind": row.get("kind"),
            "title": row.get("title"),
            "organization": row.get("organization"),
            "summary": row.get("ai_summary"),
            "stack": row.get("stack") or [],
        })
    # de-dup case-insensitively, preserve order
    seen, merged = set(), []
    for s in skills:
        k = str(s).lower()
        if k and k not in seen:
            seen.add(k)
            merged.append(s)
    augmented["skills"] = merged          # skills are experience-derived only
    augmented["experiences"] = exps        # for the LLM scorer
    augmented["_experience_count"] = len(rows)
    return augmented


def _rule_details(job: dict, profile: dict) -> tuple[float, dict]:
    rule = scorer.score_job(job, profile)
    details = {
        "rule": rule,
        "llm": None,
        "method": "rule",
        "score": rule["score"],
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }
    return rule["score"], details


def _save_details(app_id: str, score: float, details: dict):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE applications SET match_score = ?, match_details = ?, updated_at = ? WHERE id = ?",
            (score, json.dumps(details), now, app_id),
        )


def _run_scoring(task_id: str, only_unscored: bool, use_llm: bool):
    task = _score_tasks[task_id]
    try:
        task["status"] = "running"
        profile = _augment_profile(load_profile())

        with get_db() as conn:
            if only_unscored:
                rows = conn.execute(
                    "SELECT id, job_id, job_data FROM applications WHERE match_score IS NULL"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, job_id, job_data FROM applications"
                ).fetchall()

        task["total"] = len(rows)
        llm_used = use_llm and llm.is_configured()
        task["llm_used"] = llm_used

        # Phase 1: rule-score everything (fast, deterministic, no rate limits).
        scored = []  # (app_id, job, details)
        for row in rows:
            job = _parse_job(row)
            score, details = _rule_details(job, profile)
            _save_details(row["id"], score, details)
            scored.append((row["id"], job, details))
            task["done"] += 1

        # Phase 2: LLM-refine only the top-N rule candidates, gently (rate-limited).
        if llm_used and scored:
            top = sorted(scored, key=lambda t: t[2]["score"], reverse=True)[:LLM_TOP_N]
            task["llm_total"] = len(top)
            for app_id, job, details in top:
                refined = llm.llm_refine(job, profile)
                if refined:
                    details["llm"] = refined
                    details["method"] = "llm"
                    details["score"] = refined["score"]
                    _save_details(app_id, refined["score"], details)
                task["llm_done"] += 1
                time.sleep(llm.REQUEST_DELAY_SECONDS)

        task["status"] = "completed"
        task["finished_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:  # noqa: BLE001 - report failure to the poller
        task["status"] = "failed"
        task["error"] = str(e)


@router.post("/score")
def trigger_scoring(req: ScoreRunRequest):
    running = [t for t in _score_tasks.values() if t["status"] == "running"]
    if running:
        raise HTTPException(409, "A scoring run is already in progress")

    task_id = str(uuid.uuid4())[:8]
    _score_tasks[task_id] = {
        "status": "starting",
        "total": 0,
        "done": 0,
        "llm_total": 0,
        "llm_done": 0,
        "only_unscored": req.only_unscored,
        "llm_used": req.use_llm and llm.is_configured(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }
    thread = threading.Thread(
        target=_run_scoring, args=(task_id, req.only_unscored, req.use_llm), daemon=True
    )
    thread.start()
    return {"task_id": task_id, "status": "starting", "llm_available": llm.is_configured()}


@router.get("/score/{task_id}")
def get_scoring_status(task_id: str):
    if task_id not in _score_tasks:
        raise HTTPException(404, "Task not found")
    return {"task_id": task_id, **_score_tasks[task_id]}


@router.get("/score")
def scoring_overview():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM applications").fetchone()["c"]
        scored = conn.execute(
            "SELECT COUNT(*) c FROM applications WHERE match_score IS NOT NULL"
        ).fetchone()["c"]
    return {
        "llm_available": llm.is_configured(),
        "total_jobs": total,
        "scored_jobs": scored,
        "unscored_jobs": total - scored,
        "tasks": {
            k: {"status": v["status"], "done": v["done"], "total": v["total"]}
            for k, v in _score_tasks.items()
        },
    }
