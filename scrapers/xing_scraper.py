"""Xing/kununu jobs scraper using requests + BeautifulSoup."""
import time
from bs4 import BeautifulSoup
from base import (
    get_session, make_job_id, build_job_posting, submit_jobs,
    detect_remote_type, detect_job_type,
)

SEARCH_QUERIES = [
    "Software Entwickler",
    "Python Developer",
    "Webentwickler",
    "Frontend Entwickler",
]
LOCATION = "Nordrhein-Westfalen"
MAX_JOBS = 10


def scrape_xing(query, location=LOCATION):
    jobs = []
    session = get_session()

    for page in range(3):
        if len(jobs) >= MAX_JOBS:
            break
        url = (
            f"https://www.xing.com/jobs/search"
            f"?keywords={query.replace(' ', '%20')}"
            f"&location={location.replace(' ', '%20')}&page={page+1}"
        )
        print(f"[xing] Fetching: {query} - page {page + 1}")

        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"[xing] HTTP {resp.status_code}")
                break
        except Exception as e:
            print(f"[xing] Request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select('article[data-testid="job-search-result"]')
        if not cards:
            cards = soup.select('div[class*="JobSearchResult"]')
        if not cards:
            links = soup.select('a[href*="/jobs/"]')
            seen_urls = set()
            for link in links:
                if len(jobs) >= MAX_JOBS:
                    break
                href = link.get("href", "")
                if "search" in href or href in seen_urls:
                    continue
                seen_urls.add(href)
                title = link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                job_url = "https://www.xing.com" + href if href.startswith("/") else href
                job_id = make_job_id("xing", job_url)
                jobs.append(build_job_posting(
                    job_id=job_id, title=title, company="Unknown",
                    location=location, source="xing", url=job_url,
                    remote_type=detect_remote_type(title),
                    job_type=detect_job_type(title),
                ))
            break

        print(f"[xing] Found {len(cards)} cards")

        for card in cards:
            if len(jobs) >= MAX_JOBS:
                break
            try:
                title_tag = card.select_one("h2, h3")
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title:
                    continue

                link_tag = card.select_one('a[href*="/jobs/"]')
                job_url = ""
                if link_tag:
                    href = link_tag.get("href", "")
                    job_url = "https://www.xing.com" + href if href.startswith("/") else href

                company = "Unknown"
                job_location = location
                for el in card.find_all(["span", "p", "div"]):
                    text = el.get_text(strip=True)
                    if any(w in text.lower() for w in ["gmbh", "ag", "e.v.", "kg", "se"]):
                        company = text[:80]
                    elif any(w in text.lower() for w in ["nordrhein", "nrw", "koeln", "duesseldorf", "essen", "dortmund", "hessen", "frankfurt"]):
                        job_location = text[:80]

                unique_key = job_url or f"{title}-{company}"
                job_id = make_job_id("xing", unique_key)
                full_text = f"{title} {job_location}"

                jobs.append(build_job_posting(
                    job_id=job_id, title=title, company=company,
                    location=job_location, source="xing", url=job_url,
                    remote_type=detect_remote_type(full_text),
                    job_type=detect_job_type(full_text),
                ))
            except Exception as e:
                print(f"[xing] Parse error: {e}")

        time.sleep(2)
    return jobs


def main(query=None, location=None):
    queries = [query] if query else SEARCH_QUERIES
    loc = location or LOCATION
    all_jobs = []
    for q in queries:
        try:
            jobs = scrape_xing(q, location=loc)
            all_jobs.extend(jobs)
            print(f"[xing] {q}: {len(jobs)} jobs")
            if len(all_jobs) >= MAX_JOBS:
                break
        except Exception as e:
            print(f"[xing] Failed on '{q}': {e}")

    if all_jobs:
        seen = {j["id"]: j for j in all_jobs}
        unique_jobs = list(seen.values())[:MAX_JOBS]
        print(f"\n[xing] Total unique: {len(unique_jobs)}")
        submit_jobs(unique_jobs, "xing", ", ".join(queries), loc)
    else:
        print("[xing] No jobs scraped")


if __name__ == "__main__":
    main()
