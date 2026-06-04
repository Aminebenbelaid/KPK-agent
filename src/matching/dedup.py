"""Fuzzy deduplication across job sources.

The same role is often posted on LinkedIn, StepStone, Xing and Arbeitsagentur at
once. We detect near-duplicates by fuzzy-matching the normalized title + company
(and, when present, location) using the stdlib ``difflib`` — no extra dependency.

When a new job is a near-duplicate of an existing one, the caller keeps a single
canonical row and records the additional source under ``job_data.also_on`` so the
UI can show "also on StepStone, Xing" instead of three separate cards.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Optional

TITLE_THRESHOLD = 0.82
COMPANY_THRESHOLD = 0.80

# Gender markers and noise commonly attached to German job titles.
_NOISE = re.compile(
    r"\(?\s*[mwfdx]\s*[/\\|]\s*[mwfdx]\s*([/\\|]\s*[mwfdx]\s*)?\)?"  # (m/w/d), m/w/x
    r"|\bgmbh\b|\bag\b|\bse\b|\bco\b|\bkg\b|\binc\b|\bltd\b"          # company suffixes
    r"|[^\w\s]",                                                       # punctuation
    re.IGNORECASE,
)
_WS = re.compile(r"\s+")


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text.lower()
    t = _NOISE.sub(" ", t)
    t = _WS.sub(" ", t)
    return t.strip()


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def is_duplicate(job_a: dict, job_b: dict) -> tuple[bool, float]:
    """Return (is_dup, confidence) for two job dicts (with title/company/location)."""
    ta, tb = _normalize(job_a.get("title")), _normalize(job_b.get("title"))
    ca, cb = _normalize(job_a.get("company")), _normalize(job_b.get("company"))

    title_sim = _sim(ta, tb)
    company_sim = _sim(ca, cb)

    if title_sim >= TITLE_THRESHOLD and company_sim >= COMPANY_THRESHOLD:
        # Average, lightly weighted toward title.
        return True, round(title_sim * 0.6 + company_sim * 0.4, 3)
    return False, 0.0


def find_duplicate(conn, job: dict) -> Optional[dict]:
    """Find an existing application that is a near-duplicate of ``job``.

    Only considers postings from a *different* source — the same source updating
    its own posting is handled by the normal job_id upsert path.
    Returns the existing row dict (id, job_id, job_data parsed) or None.
    """
    source = job.get("source")
    rows = conn.execute(
        "SELECT id, job_id, job_data FROM applications"
    ).fetchall()

    best = None
    best_conf = 0.0
    for row in rows:
        data = row["job_data"]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                continue
        if not isinstance(data, dict):
            continue
        if data.get("source") == source and row["job_id"] != job.get("id"):
            # same source, different posting -> not a cross-source duplicate
            continue
        dup, conf = is_duplicate(job, data)
        if dup and conf > best_conf:
            best = {"id": row["id"], "job_id": row["job_id"], "job_data": data}
            best_conf = conf
    return best
