"""Agentur fuer Arbeit scraper using the official REST API.
Docs: https://github.com/bundesAPI/jobsuche-api"""
import base64
import requests
from base import make_job_id, build_job_posting, submit_jobs, detect_remote_type, detect_job_type, clean_html

API_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
DETAIL_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/"
API_KEY = "jobboerse-jobsuche"


def fetch_aa_description(ref_nr):
    """Fetch the full job description (stellenangebotsBeschreibung) for a refnr."""
    if not ref_nr:
        return ""
    try:
        enc = base64.b64encode(ref_nr.encode()).decode()
        resp = requests.get(DETAIL_URL + enc, headers={"X-API-Key": API_KEY}, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("stellenangebotsBeschreibung") or ""
    except Exception:
        pass
    return ""

SEARCH_QUERIES = [
    "Softwareentwickler",
    "Webentwickler",
    "Python Entwickler",
    "IT Junior",
    "Frontend Developer",
]
LOCATION = "Nordrhein-Westfalen"
MAX_JOBS = 10


def scrape_arbeitsagentur(query, location=LOCATION):
    headers = {"X-API-Key": API_KEY}
    params = {
        "was": query,
        "wo": location,
        "page": 1,
        "size": MAX_JOBS,
        "umkreis": 50,
        "angebotsart": 1,
    }
    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[arbeitsagentur] API request failed for '{query}': {e}")
        return []

    jobs = []
    stellenangebote = data.get("stellenangebote") or []
    total = data.get("maxErgebnisse", 0)
    print(f"[arbeitsagentur] '{query}': {len(stellenangebote)} results (of {total} total)")

    for item in stellenangebote[:MAX_JOBS]:
        try:
            ref_nr = item.get("refnr", "")
            title = item.get("titel") or ""
            if not title:
                continue

            company = item.get("arbeitgeber") or "Unknown"
            arbeitsort = item.get("arbeitsort") or {}
            ort = arbeitsort.get("ort") or ""
            region = arbeitsort.get("region") or ""
            plz = arbeitsort.get("plz") or ""
            job_location = f"{ort}, {region}".strip(", ") or location

            externe_url = item.get("externeUrl") or ""
            job_url = externe_url or (f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref_nr}" if ref_nr else "")

            beruf = item.get("beruf") or ""
            eintrittsdatum = item.get("eintrittsdatum") or ""
            posted = item.get("aktuelleVeroeffentlichungsdatum") or eintrittsdatum or None

            desc_raw = fetch_aa_description(ref_nr)
            desc_clean = clean_html(desc_raw)
            full_text = f"{title} {beruf} {job_location} {desc_clean}"

            job_id = make_job_id("arbeitsagentur", ref_nr or f"{title}-{company}")
            job = build_job_posting(
                job_id=job_id,
                title=title,
                company=company,
                location=job_location,
                source="arbeitsagentur",
                url=job_url,
                description_raw=desc_raw,
                description_clean=desc_clean,
                posted_date=posted,
                remote_type=detect_remote_type(full_text),
                job_type=detect_job_type(full_text),
                experience_level="entry",
            )
            jobs.append(job)
        except Exception as e:
            print(f"[arbeitsagentur] Parse error: {e}")

    return jobs


def main(query=None, location=None):
    queries = [query] if query else SEARCH_QUERIES
    loc = location or LOCATION
    all_jobs = []
    for q in queries:
        try:
            jobs = scrape_arbeitsagentur(q, location=loc)
            all_jobs.extend(jobs)
            print(f"[arbeitsagentur] {q}: {len(jobs)} jobs")
            if len(all_jobs) >= MAX_JOBS:
                break
        except Exception as e:
            print(f"[arbeitsagentur] Failed on '{q}': {e}")

    if all_jobs:
        seen = {j["id"]: j for j in all_jobs}
        unique_jobs = list(seen.values())[:MAX_JOBS]
        print(f"\n[arbeitsagentur] Total unique: {len(unique_jobs)}")
        submit_jobs(unique_jobs, "arbeitsagentur", ", ".join(queries), loc)
    else:
        print("[arbeitsagentur] No jobs scraped")


if __name__ == "__main__":
    main()
