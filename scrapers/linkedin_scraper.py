"""LinkedIn public job scraper using requests + BeautifulSoup.
No login required - scrapes the public job search pages."""
import re
import time
from bs4 import BeautifulSoup
from base import (
    get_session, make_job_id, build_job_posting, submit_jobs,
    detect_remote_type, detect_job_type, clean_html,
)


def fetch_linkedin_description(session, job_num_id):
    """Fetch the full job description HTML from the guest jobPosting endpoint."""
    if not job_num_id:
        return ""
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_num_id}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        node = soup.select_one(".show-more-less-html__markup, .description__text")
        return str(node) if node else ""
    except Exception:
        return ""

SEARCH_QUERIES = [
    "Software Developer",
    "Python Developer",
    "Frontend Developer",
    "Junior Entwickler",
]
LOCATION = "Nordrhein-Westfalen, Deutschland"
MAX_JOBS = 10


def scrape_linkedin(query, location=LOCATION, geo_id=None):
    """Scrape LinkedIn guest job search.

    We rely on the free-text ``location`` (which LinkedIn geocodes) rather than a
    hardcoded geoId. A geoId, if provided, OVERRIDES the location text, so we only
    send one when the caller explicitly passes a correct id for that location.
    """
    jobs = []
    session = get_session()

    for page in range(3):
        if len(jobs) >= MAX_JOBS:
            break
        start = page * 25
        url = (
            f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={query.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
            f"&start={start}"
        )
        if geo_id:
            url += f"&geoId={geo_id}"
        print(f"[linkedin] Fetching: {query} - page {page + 1}")

        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"[linkedin] HTTP {resp.status_code}")
                break
        except Exception as e:
            print(f"[linkedin] Request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("li")
        if not cards:
            print(f"[linkedin] No cards on page {page + 1}")
            break

        print(f"[linkedin] Found {len(cards)} items")

        for card in cards:
            if len(jobs) >= MAX_JOBS:
                break
            try:
                title_tag = card.select_one("h3.base-search-card__title")
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title or len(title) < 3:
                    continue

                link_tag = card.select_one("a.base-card__full-link")
                job_url = link_tag.get("href", "").split("?")[0] if link_tag else ""

                company_tag = card.select_one("h4.base-search-card__subtitle a, h4.base-search-card__subtitle")
                company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                loc_tag = card.select_one("span.job-search-card__location")
                job_location = loc_tag.get_text(strip=True) if loc_tag else location

                time_tag = card.select_one("time")
                posted_date = time_tag.get("datetime") if time_tag else None

                # numeric job id (from urn or url) -> used for the detail endpoint
                num_id = None
                urn_node = card.select_one("[data-entity-urn]")
                if urn_node:
                    m = re.search(r"jobPosting:(\d+)", urn_node.get("data-entity-urn", ""))
                    if m:
                        num_id = m.group(1)
                if not num_id:
                    m = re.search(r"-(\d{8,})", job_url)
                    num_id = m.group(1) if m else None

                desc_html = fetch_linkedin_description(session, num_id)
                desc_clean = clean_html(desc_html)

                unique_key = job_url or f"{title}-{company}-{job_location}"
                job_id = make_job_id("linkedin", unique_key)
                full_text = f"{title} {job_location} {desc_clean}"

                jobs.append(build_job_posting(
                    job_id=job_id, title=title, company=company,
                    location=job_location, source="linkedin", url=job_url,
                    description_raw=desc_html, description_clean=desc_clean,
                    posted_date=posted_date,
                    remote_type=detect_remote_type(full_text),
                    job_type=detect_job_type(full_text),
                ))
                time.sleep(0.6)
            except Exception as e:
                print(f"[linkedin] Parse error: {e}")

        time.sleep(2)
    return jobs


def main(query=None, location=None):
    queries = [query] if query else SEARCH_QUERIES
    loc = location or LOCATION
    all_jobs = []
    for q in queries:
        try:
            jobs = scrape_linkedin(q, location=loc)
            all_jobs.extend(jobs)
            print(f"[linkedin] {q}: {len(jobs)} jobs")
            if len(all_jobs) >= MAX_JOBS:
                break
        except Exception as e:
            print(f"[linkedin] Failed on '{q}': {e}")

    if all_jobs:
        seen = {j["id"]: j for j in all_jobs}
        unique_jobs = list(seen.values())[:MAX_JOBS]
        print(f"\n[linkedin] Total unique: {len(unique_jobs)}")
        submit_jobs(unique_jobs, "linkedin", ", ".join(queries), loc)
    else:
        print("[linkedin] No jobs scraped")


if __name__ == "__main__":
    main()
