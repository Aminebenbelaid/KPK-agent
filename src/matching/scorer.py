"""Weighted rule-based job scoring against a candidate profile.

Produces a 0-100 score plus a breakdown so the UI can explain *why* a job ranks
where it does. This is the deterministic baseline of the hybrid engine; the
optional LLM pass (see ``llm.py``) can refine the final score and add prose.
"""
from __future__ import annotations

import re
from typing import Optional

from src.matching.skills import extract_skills, normalize_skills

# Component weights (sum = 100).
WEIGHTS = {
    "skills": 45,
    "role": 20,
    "location": 10,
    "remote": 10,
    "seniority": 10,
    "salary": 5,
}

_WS = re.compile(r"\s+")


def _tokens(text: Optional[str]) -> set[str]:
    if not text:
        return set()
    return {t for t in _WS.split(re.sub(r"[^\w\s]", " ", text.lower())) if len(t) > 1}


def job_skills(job: dict) -> list[str]:
    """Best-effort skill list for a job: stored skills + extracted from text."""
    stored = list(job.get("skills_required") or []) + list(job.get("technologies") or [])
    extracted = extract_skills(
        job.get("title", ""),
        job.get("description_clean") or job.get("description_raw") or "",
    )
    return normalize_skills(stored + extracted)


def _score_skills(profile_skills: list[str], js: list[str]) -> tuple[float, dict]:
    """Score = fraction of the JOB's required skills that the candidate has.

    Measuring against the job's requirements (not the profile's breadth) means
    adding more skills/experience can only ever help a job's score, never hurt it.
    """
    prof = normalize_skills(profile_skills)
    prof_set = {s.lower() for s in prof}
    job_set = {s.lower() for s in js}
    matched = sorted([s for s in js if s.lower() in prof_set])   # job skills I have
    missing = sorted([s for s in js if s.lower() not in prof_set])  # job skills I lack

    if job_set:
        frac = len(matched) / len(job_set)
    elif prof:
        frac = 0.5  # candidate has skills but the job posting lists none to match
    else:
        frac = 0.6  # no signal either way
    note = None if prof else "no profile skills set"
    return frac, {"matched": matched, "missing": missing, "note": note}


def _score_role(target_roles: list[str], title: str) -> float:
    if not target_roles:
        return 0.6
    title_tokens = _tokens(title)
    for role in target_roles:
        role_tokens = _tokens(role)
        if not role_tokens:
            continue
        overlap = role_tokens & title_tokens
        if overlap and len(overlap) / len(role_tokens) >= 0.5:
            return 1.0
    return 0.0


def _score_location(profile_loc: str, job_loc: str, remote_type: str) -> float:
    if remote_type and remote_type.lower() in ("remote", "fully remote"):
        return 1.0
    if not profile_loc:
        return 0.6
    p, j = _tokens(profile_loc), _tokens(job_loc)
    if p & j:
        return 1.0
    return 0.2


def _score_remote(preferred: str, remote_type: str) -> float:
    if not preferred:
        return 0.6
    if not remote_type:
        return 0.5
    pref, rt = preferred.lower(), remote_type.lower()
    if pref in rt or rt in pref:
        return 1.0
    if pref == "hybrid" and rt in ("remote", "on-site"):
        return 0.7
    return 0.3


_LEVEL_YEARS = {
    "intern": 0, "internship": 0, "praktikum": 0,
    "junior": 1, "entry": 1, "entry-level": 1, "einsteiger": 1,
    "mid": 3, "intermediate": 3, "professional": 3,
    "senior": 6, "lead": 8, "principal": 10, "staff": 9,
}


def _infer_level(text: str) -> Optional[int]:
    if not text:
        return None
    low = text.lower()
    for kw, yrs in _LEVEL_YEARS.items():
        if kw in low:
            return yrs
    return None


def _score_seniority(years: int, job: dict) -> float:
    level_text = (job.get("experience_level") or "") + " " + (job.get("title") or "")
    target = _infer_level(level_text)
    if target is None:
        return 0.6
    diff = abs((years or 0) - target)
    if diff <= 1:
        return 1.0
    if diff <= 3:
        return 0.6
    return 0.25


def _score_salary(min_salary: Optional[float], job: dict) -> float:
    if not min_salary:
        return 0.6
    job_min = job.get("salary_min")
    job_max = job.get("salary_max")
    ref = job_max or job_min
    if not ref:
        return 0.5
    if ref >= min_salary:
        return 1.0
    return max(0.1, ref / min_salary)


def score_job(job: dict, profile: dict) -> dict:
    """Return {'score': float(0-100), 'breakdown': {...}, 'method': 'rule'}."""
    profile = profile or {}
    js = job_skills(job)

    skill_frac, skill_detail = _score_skills(profile.get("skills") or [], js)
    role_frac = _score_role(profile.get("target_roles") or [], job.get("title", ""))
    loc_frac = _score_location(
        profile.get("location") or "", job.get("location") or "", job.get("remote_type") or ""
    )
    remote_frac = _score_remote(
        profile.get("preferred_remote_type") or "", job.get("remote_type") or ""
    )
    sen_frac = _score_seniority(profile.get("experience_years") or 0, job)
    sal_frac = _score_salary(profile.get("min_salary"), job)

    components = {
        "skills": skill_frac,
        "role": role_frac,
        "location": loc_frac,
        "remote": remote_frac,
        "seniority": sen_frac,
        "salary": sal_frac,
    }
    points = {k: round(v * WEIGHTS[k], 1) for k, v in components.items()}
    total = round(sum(points.values()), 1)

    return {
        "score": total,
        "method": "rule",
        "breakdown": {
            "points": points,
            "weights": WEIGHTS,
            "skills_matched": skill_detail.get("matched", []),
            "skills_missing": skill_detail.get("missing", []),
            "job_skills": js,
        },
    }
