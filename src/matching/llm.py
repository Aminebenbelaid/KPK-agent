"""Optional LLM refinement of job match scores via the Kisski (OpenAI-compatible) API.

This is the second half of the hybrid engine. If a Kisski API key is configured
(in the settings table or environment), we ask the model to read the job and the
candidate profile and return a 0-100 score plus a one/two-sentence explanation.
If the key is missing or the call fails, callers fall back to the rule-based score.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

import requests

from src.config import get_settings

# Kisski academic cloud enforces strict rate limits; space calls out and back off on 429.
REQUEST_DELAY_SECONDS = 1.5
MAX_RETRIES = 3


def _setting(key: str) -> Optional[str]:
    """Read a value from the settings table, if present."""
    try:
        db_path = Path(get_settings().TRACKER_DB_PATH)
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()
        if row and row[0]:
            return row[0]
    except sqlite3.Error:
        pass
    return None


def _resolve(key_setting: str, attr: str) -> str:
    """Prefer the DB setting, fall back to the config/env value."""
    val = _setting(key_setting)
    if val:
        return val
    return getattr(get_settings(), attr, "") or ""


def get_config() -> dict:
    return {
        "api_key": _resolve("kisski_api_key", "KISSKI_API_KEY"),
        "base_url": _resolve("kisski_base_url", "KISSKI_BASE_URL").rstrip("/"),
        "model": _resolve("llm_model", "LLM_MODEL"),
    }


def is_configured() -> bool:
    return bool(get_config()["api_key"])


def _profile_summary(profile: dict) -> str:
    parts = []
    if profile.get("target_roles"):
        parts.append("Target roles: " + ", ".join(profile["target_roles"]))
    if profile.get("experience_years"):
        parts.append(f"Total experience: {profile['experience_years']} years")
    if profile.get("location"):
        parts.append("Preferred location: " + str(profile["location"]))
    if profile.get("preferred_remote_type"):
        parts.append("Remote preference: " + str(profile["preferred_remote_type"]))
    if profile.get("min_salary"):
        parts.append(f"Minimum salary: {profile['min_salary']}")

    exps = profile.get("experiences") or []
    if exps:
        parts.append("\nExperience & projects:")
        for e in exps[:12]:
            stack = ", ".join(e.get("stack") or [])
            line = f"- [{e.get('kind', 'job')}] {e.get('title', '')}"
            if e.get("organization"):
                line += f" @ {e['organization']}"
            if e.get("summary"):
                line += f" — {e['summary']}"
            if stack:
                line += f" (stack: {stack})"
            parts.append(line)
    elif profile.get("skills"):
        parts.append("Skills: " + ", ".join(profile["skills"]))

    return "\n".join(parts) or "(no profile details provided)"


def _job_summary(job: dict) -> str:
    desc = (job.get("description_clean") or job.get("description_raw") or "")[:1500]
    return (
        f"Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Remote: {job.get('remote_type', '')}\n"
        f"Description: {desc}"
    )


_PROMPT = """You are a career assistant scoring how well a job fits a candidate.
Consider skills overlap, role/title relevance, seniority fit, location and remote preference.

CANDIDATE PROFILE:
{profile}

JOB POSTING:
{job}

Respond with ONLY a JSON object, no markdown, in exactly this form:
{{"score": <integer 0-100>, "explanation": "<one or two sentences>"}}"""


def _extract_json(text: str) -> Optional[dict]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except (ValueError, TypeError):
        return None


def extract_json_any(text: str):
    """Extract the first JSON object OR array from a model response."""
    if not text:
        return None
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except (ValueError, TypeError):
        return None


def chat(messages, max_tokens: int = 400, temperature: float = 0.2,
         timeout: int = 60) -> Optional[str]:
    """Generic chat completion against the configured Kisski model.

    Returns the assistant message content, or None on failure. Handles 429
    rate-limiting with exponential backoff.
    """
    cfg = get_config()
    if not cfg["api_key"]:
        return None
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                f"{cfg['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            if resp.status_code == 429:
                time.sleep(2 ** attempt * 2)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, ValueError, IndexError):
            return None
    return None


def llm_refine(job: dict, profile: dict, timeout: int = 45) -> Optional[dict]:
    """Return {'score': float, 'explanation': str, 'method': 'llm'} or None on failure."""
    cfg = get_config()
    if not cfg["api_key"]:
        return None

    content = chat(
        [
            {"role": "system", "content": "You score job-candidate fit. Output JSON only."},
            {
                "role": "user",
                "content": _PROMPT.format(
                    profile=_profile_summary(profile), job=_job_summary(job)
                ),
            },
        ],
        max_tokens=200,
        temperature=0.2,
        timeout=timeout,
    )
    if content is None:
        return None

    parsed = _extract_json(content)
    if not parsed or "score" not in parsed:
        return None
    try:
        score = float(parsed["score"])
    except (ValueError, TypeError):
        return None
    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
        "explanation": str(parsed.get("explanation", "")).strip(),
        "method": "llm",
    }
