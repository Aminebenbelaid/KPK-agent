"""Base scraper utilities shared by all job board scrapers."""
import hashlib
import json
import time
import requests
from datetime import datetime
from typing import List, Optional

API_BASE = "http://localhost:8000"
API_KEY = "change-me-to-a-long-random-string"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
}


def get_session():
    """Create a requests session with default headers."""
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def make_job_id(source, unique_key):
    short_hash = hashlib.md5(unique_key.encode()).hexdigest()[:8]
    return f"{source}-{short_hash}"


def build_job_posting(
    job_id,
    title,
    company,
    location,
    source,
    url=None,
    description_raw=None,
    description_clean=None,
    posted_date=None,
    salary_min=None,
    salary_max=None,
    job_type="full-time",
    remote_type="on-site",
    skills_required=None,
    experience_level="entry",
    technologies=None,
):
    return {
        "id": job_id,
        "title": title,
        "company": company,
        "location": location or "",
        "source": source,
        "url": url or "",
        "description_raw": description_raw or "",
        "description_clean": description_clean or "",
        "posted_date": posted_date,
        "scraped_date": datetime.utcnow().isoformat(),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": "EUR",
        "job_type": job_type,
        "remote_type": remote_type,
        "skills_required": skills_required or [],
        "experience_level": experience_level,
        "technologies": technologies or [],
        "is_duplicate": False,
        "quality_score": 0.0,
        "match_score": None,
    }


def submit_jobs(jobs, source, query, location):
    if not jobs:
        print(f"[{source}] No jobs to submit")
        return {}

    start = time.time()
    headers = {"X-Internal-Api-Key": API_KEY, "Content-Type": "application/json"}

    try:
        result = requests.post(
            f"{API_BASE}/api/internal/jobs/batch",
            headers=headers,
            json={"jobs": jobs},
            timeout=30,
        )
        batch_result = result.json()
    except Exception as e:
        print(f"[{source}] Failed to submit jobs: {e}")
        return {}

    elapsed = time.time() - start

    try:
        requests.post(
            f"{API_BASE}/api/internal/search-history",
            headers=headers,
            json={
                "query": query,
                "location": location,
                "sources_used": [source],
                "results_count": len(jobs),
                "new_jobs_count": batch_result.get("inserted", 0),
                "execution_time_seconds": round(elapsed, 2),
            },
            timeout=10,
        )
    except Exception:
        pass

    print(
        f"[{source}] Submitted {len(jobs)} jobs: "
        f"{batch_result.get('inserted', 0)} new, "
        f"{batch_result.get('updated', 0)} updated, "
        f"{len(batch_result.get('errors', []))} errors"
    )
    return batch_result


def clean_html(html_text):
    if not html_text:
        return ""
    import re
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_detail_html(session, url, timeout=15):
    """GET a job detail page, returning HTML text or '' on failure."""
    if not url:
        return ""
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code == 200:
            # Fix mojibake: trust the bytes' detected encoding when the server
            # declares none or a wrong (latin-1) charset.
            if not resp.encoding or resp.encoding.lower() in ("iso-8859-1", "latin-1"):
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
    except Exception:
        pass
    return ""


def extract_jsonld_description(html):
    """Extract a JobPosting description from JSON-LD (used by StepStone/Xing/most boards)."""
    if not html:
        return ""
    import json
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        # also look one level into @graph
        expanded = []
        for it in items:
            if isinstance(it, dict) and isinstance(it.get("@graph"), list):
                expanded.extend(it["@graph"])
            else:
                expanded.append(it)
        for it in expanded:
            if isinstance(it, dict) and it.get("description"):
                t = it.get("@type", "")
                types = t if isinstance(t, list) else [t]
                if any("JobPosting" in str(x) for x in types):
                    return it["description"]
    return ""


def detect_remote_type(text):
    lower = (text or "").lower()
    if "remote" in lower or "homeoffice" in lower or "home office" in lower:
        if "hybrid" in lower:
            return "hybrid"
        return "remote"
    return "on-site"


def detect_job_type(text):
    lower = (text or "").lower()
    if "teilzeit" in lower or "part-time" in lower or "part time" in lower:
        return "part-time"
    if "praktikum" in lower or "internship" in lower:
        return "internship"
    if "werkstudent" in lower or "working student" in lower:
        return "working-student"
    if "freelance" in lower:
        return "freelance"
    if "minijob" in lower or "mini-job" in lower:
        return "minijob"
    return "full-time"
