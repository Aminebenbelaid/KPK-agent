"""CV parsing and experience intelligence (LLM-powered).

Three jobs:
  * ``extract_pdf_text`` / accept raw text  -> plain text of a CV
  * ``parse_cv``            -> structured experiences/projects for the review popup
  * ``enrich_experience``   -> AI understanding (summary + tags) of a manual entry
  * ``match_experiences_to_job`` -> rank which experiences best fit a given job
"""
from __future__ import annotations

import json
from typing import Optional

from src.matching import llm
from src.matching.skills import normalize_skills


def extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF byte string. Returns '' if it cannot be read."""
    try:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - skip unreadable pages
                continue
        return "\n".join(parts).strip()
    except Exception:  # noqa: BLE001 - pypdf missing or corrupt file
        return ""


_PARSE_PROMPT = """You are a CV parser. Read the CV text below and extract every
work experience and notable project the candidate has.

For EACH item return an object with:
- "kind": "job" or "project"
- "title": role title or project name
- "organization": company / client / context (empty string if none)
- "description": 1-3 sentences on what they did and achieved
- "stack": array of concrete technologies/tools/skills used
- "start_date": "YYYY-MM" or "" if unknown
- "end_date": "YYYY-MM" or "present" or "" if unknown
- "ai_summary": one short sentence describing the TYPE of experience (e.g. "Backend API development in Python")
- "ai_tags": array of 1-4 high-level category tags (e.g. ["backend","data","devops"])

Return ONLY a JSON array of these objects, no markdown, no commentary.

CV TEXT:
{text}"""


def parse_cv(text: str) -> list[dict]:
    """Parse raw CV text into a list of structured experience dicts (not saved)."""
    if not text or not text.strip():
        return []
    content = llm.chat(
        [
            {"role": "system", "content": "You extract structured data from CVs. Output JSON only."},
            {"role": "user", "content": _PARSE_PROMPT.format(text=text[:12000])},
        ],
        max_tokens=2000,
        temperature=0.1,
        timeout=120,
    )
    parsed = llm.extract_json_any(content) if content else None
    if not isinstance(parsed, list):
        return []
    return [_clean_experience(item) for item in parsed if isinstance(item, dict)]


def _clean_experience(item: dict) -> dict:
    kind = item.get("kind", "job")
    if kind not in ("job", "project"):
        kind = "job"
    return {
        "kind": kind,
        "title": str(item.get("title", "")).strip() or "Untitled",
        "organization": str(item.get("organization", "") or "").strip(),
        "description": str(item.get("description", "") or "").strip(),
        "stack": normalize_skills(item.get("stack") or []),
        "start_date": str(item.get("start_date", "") or "").strip() or None,
        "end_date": str(item.get("end_date", "") or "").strip() or None,
        "ai_summary": str(item.get("ai_summary", "") or "").strip(),
        "ai_tags": [str(t).strip() for t in (item.get("ai_tags") or []) if str(t).strip()][:4],
        "source": "cv",
    }


_ENRICH_PROMPT = """Given this experience entry, infer what the person actually did
and what type of experience it represents.

Title: {title}
Organization: {organization}
Description: {description}
Stack: {stack}

Return ONLY a JSON object:
{{"ai_summary": "<one short sentence on the type of experience>",
  "ai_tags": ["<1-4 high-level category tags like backend, frontend, data, devops, ml, mobile>"],
  "stack": ["<cleaned/normalized list of technologies you can infer from the entry>"]}}"""


def enrich_experience(title: str, description: str, stack: list[str],
                      organization: str = "") -> Optional[dict]:
    """Use the LLM to summarise a manual experience entry. None if unavailable."""
    content = llm.chat(
        [
            {"role": "system", "content": "You classify professional experience. Output JSON only."},
            {
                "role": "user",
                "content": _ENRICH_PROMPT.format(
                    title=title or "",
                    organization=organization or "",
                    description=description or "",
                    stack=", ".join(stack or []),
                ),
            },
        ],
        max_tokens=300,
        temperature=0.2,
    )
    parsed = llm.extract_json_any(content) if content else None
    if not isinstance(parsed, dict):
        return None
    merged_stack = normalize_skills(list(stack or []) + list(parsed.get("stack") or []))
    return {
        "ai_summary": str(parsed.get("ai_summary", "") or "").strip(),
        "ai_tags": [str(t).strip() for t in (parsed.get("ai_tags") or []) if str(t).strip()][:4],
        "stack": merged_stack,
    }


_MATCH_PROMPT = """You help a candidate decide which of their experiences to highlight
when applying to a job.

JOB:
{job}

CANDIDATE EXPERIENCES (id :: title :: summary :: stack):
{experiences}

Pick the experiences most relevant to this job, best first. For each chosen one give
a short reason it is relevant. Return ONLY a JSON object:
{{"matches": [{{"id": "<experience id>", "relevance": <0-100>, "reason": "<one sentence>"}}],
  "overall": "<one sentence on how well this candidate's background fits the job>"}}"""


def match_experiences_to_job(job: dict, experiences: list[dict]) -> Optional[dict]:
    """Rank which experiences best fit the job. None if LLM unavailable/failed."""
    if not experiences:
        return {"matches": [], "overall": "No experiences on file yet."}

    lines = []
    for e in experiences:
        stack = ", ".join(e.get("stack") or [])
        lines.append(
            f"{e['id']} :: {e.get('title','')} :: {e.get('ai_summary') or e.get('description','')[:120]} :: {stack}"
        )
    job_summary = (
        f"Title: {job.get('title','')}\n"
        f"Company: {job.get('company','')}\n"
        f"Skills/keywords: {', '.join(job.get('skills_required') or [])}\n"
        f"Description: {(job.get('description_clean') or '')[:800]}"
    )
    content = llm.chat(
        [
            {"role": "system", "content": "You match candidate experience to jobs. Output JSON only."},
            {"role": "user", "content": _MATCH_PROMPT.format(job=job_summary, experiences="\n".join(lines))},
        ],
        max_tokens=700,
        temperature=0.2,
    )
    parsed = llm.extract_json_any(content) if content else None
    if not isinstance(parsed, dict):
        return None
    # Keep only matches that reference real experience ids.
    valid_ids = {e["id"] for e in experiences}
    matches = [
        {
            "id": m.get("id"),
            "relevance": max(0, min(100, int(m.get("relevance", 0) or 0))),
            "reason": str(m.get("reason", "") or "").strip(),
        }
        for m in (parsed.get("matches") or [])
        if isinstance(m, dict) and m.get("id") in valid_ids
    ]
    matches.sort(key=lambda m: m["relevance"], reverse=True)
    return {"matches": matches, "overall": str(parsed.get("overall", "") or "").strip()}
