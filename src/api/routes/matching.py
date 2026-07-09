"""Job-to-profile scoring endpoints (hybrid rule-based + optional LLM)."""
import json
import time
import uuid
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from src.database import get_db
from src.api.routes.profile import load_profile
from src.models.schemas import ScoreRunRequest
from src.matching import scorer, llm, rerank
from src import task_queue

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


def _augment_profile(profile: dict, sid: str) -> dict:
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
            "SELECT kind, title, organization, stack, ai_summary, ai_tags FROM experiences WHERE session_id = ?",
            (sid,),
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rule_details(job: dict, profile: dict) -> dict:
    rule = scorer.score_job(job, profile)
    return {
        "rule": rule, "llm": None, "boost": 0.0, "boost_skills": [],
        "method": "rule", "score": rule["score"], "scored_at": _now(),
    }


def _inputs_hash(job: dict, profile: dict) -> str:
    """Fingerprint the inputs that affect a score, so unchanged jobs can be skipped."""
    core = {
        "t": job.get("title"), "c": job.get("company"),
        "sk": sorted(job.get("skills_required") or []),
        "d": (job.get("description_clean") or job.get("description_raw") or "")[:400],
        "rem": job.get("remote_type"), "loc_j": job.get("location"),
        "ps": sorted(profile.get("skills") or []),
        "tr": sorted(profile.get("target_roles") or []),
        "loc": profile.get("location"), "pref": profile.get("preferred_remote_type"),
        "yrs": profile.get("experience_years"), "sal": profile.get("min_salary"),
        "sh": profile.get("success_hint"),
    }
    return hashlib.sha1(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _finalize(details: dict, job: dict, signal: dict) -> float:
    """Apply the past-success boost and set the final score + method."""
    pts, matched = rerank.boost_for(scorer.job_skills(job), signal)
    base = details["llm"]["score"] if details.get("llm") else details["rule"]["score"]
    details["boost"] = pts
    details["boost_skills"] = matched
    details["method"] = "llm" if details.get("llm") else "rule"
    details["score"] = round(min(100.0, base + pts), 1)
    return details["score"]


def _save_details(app_id: str, score: float, details: dict):
    with get_db() as conn:
        conn.execute(
            "UPDATE applications SET match_score = ?, match_details = ?, updated_at = ? WHERE id = ?",
            (score, json.dumps(details), _now(), app_id),
        )


def _prior_details(row) -> dict:
    p = row.get("match_details")
    if isinstance(p, str):
        try:
            return json.loads(p)
        except (ValueError, TypeError):
            return {}
    return p or {}


def _run_scoring(task_id: str, sid: str, only_unscored: bool, use_llm: bool):
    with llm.for_session(sid):
        _run_scoring_scoped(task_id, sid, only_unscored, use_llm)


def _run_scoring_scoped(task_id: str, sid: str, only_unscored: bool, use_llm: bool):
    task = _score_tasks[task_id]
    try:
        task["status"] = "running"
        profile = _augment_profile(load_profile(sid), sid)

        with get_db() as conn:
            signal = rerank.success_signal(conn, sid)
            profile["success_hint"] = rerank.summary(signal)
            where = "WHERE session_id = ?" + (" AND match_score IS NULL" if only_unscored else "")
            rows = conn.execute(
                f"SELECT id, job_id, job_data, match_details FROM applications {where}",
                (sid,),
            ).fetchall()

        task["total"] = len(rows)
        llm_used = use_llm and llm.is_configured()
        task["llm_used"] = llm_used
        task["llm_reused"] = 0

        # Phase 1: rule-score + re-rank boost everything. Reuse a cached LLM verdict
        # when the inputs are unchanged (saves API calls / cost).
        scored = []  # (app_id, job, details, has_llm)
        for row in rows:
            job = _parse_job(row)
            prior = _prior_details(row)
            h = _inputs_hash(job, profile)
            details = _rule_details(job, profile)
            details["inputs_hash"] = h
            if prior.get("inputs_hash") == h and prior.get("llm"):
                details["llm"] = prior["llm"]  # reuse, no API call
            final = _finalize(details, job, signal)
            _save_details(row["id"], final, details)
            scored.append((row["id"], job, details, bool(details.get("llm"))))
            task["done"] += 1

        task["llm_reused"] = sum(1 for s in scored if s[3])

        # Phase 2: LLM-refine the top candidates that don't already have a verdict.
        if llm_used and scored:
            need = [s for s in scored if not s[3]]
            top = sorted(need, key=lambda t: t[2]["score"], reverse=True)[:LLM_TOP_N]
            task["llm_total"] = len(top)
            for app_id, job, details, _ in top:
                refined = llm.llm_refine(job, profile)
                if refined:
                    details["llm"] = refined
                    final = _finalize(details, job, signal)
                    _save_details(app_id, final, details)
                task["llm_done"] += 1
                time.sleep(llm.REQUEST_DELAY_SECONDS)

        task["status"] = "completed"
        task["finished_at"] = _now()
    except Exception as e:  # noqa: BLE001 - report failure to the poller
        task["status"] = "failed"
        task["error"] = str(e)


@router.post("/score")
def trigger_scoring(request: Request, req: ScoreRunRequest):
    sid = request.state.effective_sid
    for t in _score_tasks.values():
        if t.get("sid") == sid and t["status"] in ("queued", "running"):
            raise HTTPException(409, "You already have a scoring run queued or running")

    task_id = str(uuid.uuid4())[:8]
    _score_tasks[task_id] = {
        "status": "queued",
        "sid": sid,
        "total": 0,
        "done": 0,
        "llm_total": 0,
        "llm_done": 0,
        "only_unscored": req.only_unscored,
        "llm_used": req.use_llm and llm.is_configured_for(sid),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
        "queue_id": None,
    }
    sub = task_queue.submit(
        "score",
        lambda: _run_scoring(task_id, sid, req.only_unscored, req.use_llm),
        sid=sid,
    )
    _score_tasks[task_id]["queue_id"] = sub["task_id"]
    return {
        "task_id": task_id, "status": "queued", "position": sub["position"],
        "llm_available": llm.is_configured_for(sid),
    }


@router.get("/score/{task_id}")
def get_scoring_status(request: Request, task_id: str):
    task = _score_tasks.get(task_id)
    if not task or task.get("sid") != request.state.effective_sid:
        raise HTTPException(404, "Task not found")
    out = {k: v for k, v in task.items() if k not in ("sid", "queue_id")}
    out["position"] = task_queue.position(task["queue_id"]) if task.get("queue_id") else 0
    return {"task_id": task_id, **out}


@router.get("/score")
def scoring_overview(request: Request):
    sid = request.state.effective_sid
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) c FROM applications WHERE session_id = ?", (sid,)
        ).fetchone()["c"]
        scored = conn.execute(
            "SELECT COUNT(*) c FROM applications WHERE session_id = ? AND match_score IS NOT NULL",
            (sid,),
        ).fetchone()["c"]
    return {
        "llm_available": llm.is_configured_for(sid),
        "total_jobs": total,
        "scored_jobs": scored,
        "unscored_jobs": total - scored,
        "tasks": {
            k: {"status": v["status"], "done": v["done"], "total": v["total"]}
            for k, v in _score_tasks.items() if v.get("sid") == sid
        },
    }
