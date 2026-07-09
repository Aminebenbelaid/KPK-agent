"""Market trend report: aggregate scraped jobs into demand/salary/location stats."""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from src.matching import llm


def _city(loc: Optional[str]) -> str:
    if not loc:
        return ""
    return re.split(r"[,/(]", loc)[0].strip()


def build_report(jobs: list[dict], query: Optional[str] = None) -> dict:
    """jobs: list of job_data dicts. Returns aggregated market stats + an LLM summary."""
    total = len(jobs)
    skills = Counter()
    companies = Counter()
    locations = Counter()
    remote = Counter()
    sal_lo, sal_hi = [], []

    for j in jobs:
        for s in (j.get("skills_required") or []):
            skills[s] += 1
        if j.get("company"):
            companies[j["company"]] += 1
        c = _city(j.get("location"))
        if c:
            locations[c] += 1
        remote[(j.get("remote_type") or "unknown").lower()] += 1
        if j.get("salary_min"):
            sal_lo.append(j["salary_min"])
        if j.get("salary_max"):
            sal_hi.append(j["salary_max"])

    salary = None
    if sal_lo or sal_hi:
        lows = sorted(sal_lo)
        highs = sorted(sal_hi)
        salary = {
            "count": len(sal_lo) + len(sal_hi),
            "min": int(min(sal_lo)) if sal_lo else None,
            "max": int(max(sal_hi)) if sal_hi else None,
            "median_low": int(lows[len(lows) // 2]) if lows else None,
            "median_high": int(highs[len(highs) // 2]) if highs else None,
        }

    report = {
        "query": query,
        "total_jobs": total,
        "top_skills": [{"name": k, "count": v} for k, v in skills.most_common(12)],
        "top_companies": [{"name": k, "count": v} for k, v in companies.most_common(8)],
        "top_locations": [{"name": k, "count": v} for k, v in locations.most_common(8)],
        "remote_split": dict(remote),
        "salary": salary,
        "summary": _summary(total, skills, locations, remote, salary, query),
    }
    return report


def _summary(total, skills, locations, remote, salary, query) -> str:
    if not total:
        return "No jobs to analyze yet."
    if not llm.is_configured():
        top = ", ".join(k for k, _ in skills.most_common(5))
        return f"{total} jobs analyzed. Most requested skills: {top}." if top else f"{total} jobs analyzed."

    facts = (
        f"Jobs: {total}. "
        f"Top skills: {', '.join(f'{k} ({v})' for k, v in skills.most_common(8))}. "
        f"Top locations: {', '.join(f'{k} ({v})' for k, v in locations.most_common(5))}. "
        f"Remote split: {dict(remote)}. "
        f"Salary: {salary}."
    )
    text = llm.chat(
        [
            {"role": "system", "content": "You are a job-market analyst. 2-3 sentences, concrete, no fluff. Plain text only — no markdown, asterisks, or bullet points."},
            {"role": "user", "content": f"Summarize this job-market snapshot{' for ' + query if query else ''}:\n{facts}"},
        ],
        max_tokens=180, temperature=0.3, timeout=60,
    )
    if not text:
        top = ", ".join(k for k, _ in skills.most_common(5))
        return f"{total} jobs analyzed. Most requested skills: {top}."
    return text.strip()
