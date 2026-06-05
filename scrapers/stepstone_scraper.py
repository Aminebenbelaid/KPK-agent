"""StepStone.de scraper using requests + BeautifulSoup."""
import time
from bs4 import BeautifulSoup
from base import (
    get_session, make_job_id, build_job_posting, submit_jobs,
    detect_remote_type, detect_job_type, clean_html,
    fetch_detail_html, extract_jsonld_description,
)

SEARCH_QUERIES = [
    "Software Entwickler",
    "Python Developer",
    "Webentwickler",
    "Frontend Developer",
    "Junior Developer",
]
LOCATION = "Nordrhein-Westfalen"
MAX_JOBS = 10


def scrape_stepstone(query, location=LOCATION):
    jobs = []
    session = get_session()
    encoded_q = query.replace(" ", "-").lower()
    encoded_l = location.replace(" ", "-").lower()

    for page in range(3):
        if len(jobs) >= MAX_JOBS:
            break
        url = f"https://www.stepstone.de/jobs/{encoded_q}/in-{encoded_l}?page={page+1}&radius=50"
        print(f"[stepstone] Fetching: {query} - page {page + 1}")

        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"[stepstone] HTTP {resp.status_code}")
                break
        except Exception as e:
            print(f"[stepstone] Request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("article") or soup.select('[data-testid="job-item"]')
        if not cards:
            print(f"[stepstone] No cards on page {page + 1}")
            break

        print(f"[stepstone] Found {len(cards)} cards")

        for card in cards:
            if len(jobs) >= MAX_JOBS:
                break
            try:
                title_tag = card.select_one("h2, h3")
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title or len(title) < 3:
                    continue

                link_tag = card.select_one('a[href*="/stellenangebote"], a[href*="/jobs/"]')
                if not link_tag:
                    link_tag = card.select_one("a[href]")
                job_url = ""
                if link_tag:
                    href = link_tag.get("href", "")
                    job_url = "https://www.stepstone.de" + href if href.startswith("/") else href

                company = "Unknown"
                job_location = location
                for span in card.find_all(["span", "div", "p"]):
                    text = span.get_text(strip=True)
                    if any(w in text.lower() for w in ["gmbh", "ag", "e.v.", "kg", "se", "ltd"]):
                        company = text[:80]
                    elif any(w in text.lower() for w in ["nordrhein", "nrw", "koeln", "duesseldorf", "essen", "dortmund", "bonn", "hessen", "frankfurt"]):
                        job_location = text[:80]

                desc_raw = extract_jsonld_description(fetch_detail_html(session, job_url))
                desc_clean = clean_html(desc_raw)

                unique_key = job_url or f"{title}-{company}"
                job_id = make_job_id("stepstone", unique_key)
                full_text = f"{title} {job_location} {desc_clean}"

                jobs.append(build_job_posting(
                    job_id=job_id, title=title, company=company,
                    location=job_location, source="stepstone", url=job_url,
                    description_raw=desc_raw, description_clean=desc_clean,
                    remote_type=detect_remote_type(full_text),
                    job_type=detect_job_type(full_text),
                ))
                time.sleep(0.8)
            except Exception as e:
                print(f"[stepstone] Parse error: {e}")

        time.sleep(1.5)
    return jobs


def main(query=None, location=None):
    queries = [query] if query else SEARCH_QUERIES
    loc = location or LOCATION
    all_jobs = []
    for q in queries:
        try:
            jobs = scrape_stepstone(q, location=loc)
            all_jobs.extend(jobs)
            print(f"[stepstone] {q}: {len(jobs)} jobs")
            if len(all_jobs) >= MAX_JOBS:
                break
        except Exception as e:
            print(f"[stepstone] Failed on '{q}': {e}")

    if all_jobs:
        seen = {j["id"]: j for j in all_jobs}
        unique_jobs = list(seen.values())[:MAX_JOBS]
        print(f"\n[stepstone] Total unique: {len(unique_jobs)}")
        submit_jobs(unique_jobs, "stepstone", ", ".join(queries), loc)
    else:
        print("[stepstone] No jobs scraped")


if __name__ == "__main__":
    main()
