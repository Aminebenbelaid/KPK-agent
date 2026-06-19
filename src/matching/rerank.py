"""Re-ranking from past outcomes: learn which kinds of jobs got positive responses."""
from __future__ import annotations

import json
from collections import Counter

# Statuses that indicate a positive response from an employer.
POSITIVE = {"phone_screen", "interview", "technical_test", "onsite", "offer", "accepted"}

MAX_BOOST = 8.0  # points added on top of the 0-100 score


def _parse(jd):
    if isinstance(jd, str):
        try:
            return json.loads(jd)
        except (ValueError, TypeError):
            return {}
    return jd or {}


def success_signal(conn) -> dict:
    """Aggregate skills/titles from applications that got a positive response."""
    rows = conn.execute(
        f"SELECT job_data FROM applications WHERE status IN ({','.join(['?'] * len(POSITIVE))})",
        tuple(POSITIVE),
    ).fetchall()
    skills = Counter()
    titles = []
    for r in rows:
        d = _parse(r.get("job_data") if isinstance(r, dict) else r[0])
        for s in (d.get("skills_required") or []):
            skills[s.lower()] += 1
        if d.get("title"):
            titles.append(d["title"])
    return {"count": len(rows), "skills": skills, "titles": titles[:8]}


def boost_for(job_skills: list, signal: dict) -> tuple[float, list]:
    """Bonus points for a job that shares skills with past successful applications."""
    if not signal or not signal.get("count"):
        return 0.0, []
    sset = {s.lower() for s in (job_skills or [])}
    matched = sorted([s for s in signal["skills"] if s in sset])
    pts = round(min(MAX_BOOST, len(matched) * 2.0), 1)
    return pts, matched


def summary(signal: dict) -> str:
    if not signal or not signal.get("count"):
        return ""
    top = ", ".join(k for k, _ in signal["skills"].most_common(6))
    return f"{signal['count']} past application(s) got responses; common skills: {top}."
