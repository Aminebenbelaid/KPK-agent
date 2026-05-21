"""Indeed.de scraper using requests + BeautifulSoup.
Indeed blocks plain requests aggressively. This scraper uses
the Indeed RSS-like feed and alternative endpoints."""
import time
import re
from bs4 import BeautifulSoup
from base import (
    get_session, make_job_id, build_job_posting, submit_jobs,
    clean_html, detect_remote_type, detect_job_type,
)

SEARCH_QUERIES = [
    "Software Developer",
    "Python Developer",
    "Webentwickler",
    "Frontend Developer",
    "Junior Entwickler",
]
LOCATION = "Nordrhein-Westfalen"
MAX_JOBS = 10


def scrape_indeed(query, location=LOCATION):
    jobs = []
    session = get_session()
    # Indeed serves different content based on User-Agent; try mobile UA
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
    )

    for page in range(3):
        if len(jobs) >= MAX_JOBS:
            break
        start = page * 10
        url = f"https://de.indeed.com/jobs?q={query.replace(' ', '+')}&l={location.replace(' ', '+')}&start={start}"
        print(f"[indeed] Fetching: {query} - page {page + 1}")

        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            if resp.status_code == 403:
                print(f"[indeed] Blocked (403), trying alternate endpoint")
                # Try the viewjob search endpoint
                alt_url = f"https://de.indeed.com/m/jobs?q={query.replace(' ', '+')}&l={location.replace(' ', '+')}&start={start}"
                resp = session.get(alt_url, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                print(f"[indeed] HTTP {resp.status_code}")
                break
        except Exception as e:
            print(f"[indeed] Request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try multiple card selectors (Indeed changes DOM frequently)
        cards = (
            soup.select("div.job_seen_beacon")
            or soup.select('div[class*="jobCard"]')
            or soup.select("td.resultContent")
            or soup.select('a[data-jk]')
            or soup.select('div[class*="tapItem"]')
        )
        if not cards:
            # Last resort: find all links that look like job listings
            all_links = soup.select('a[href*="/viewjob"], a[href*="/rc/clk"]')
            if all_links:
                print(f"[indeed] Found {len(all_links)} job links (fallback)")
                seen_titles = set()
                for link in all_links:
                    if len(jobs) >= MAX_JOBS:
                        break
                    title = link.get_text(strip=True)
                    if not title or len(title) < 5 or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    href = link.get("href", "")
                    if href.startswith("/"):
                        href = "https://de.indeed.com" + href
                    jk = re.search(r'jk=([a-f0-9]+)', href)
                    unique_key = jk.group(1) if jk else f"{title}"
                    job_id = make_job_id("indeed", unique_key)
                    jobs.append(build_job_posting(
                        job_id=job_id, title=title, company="Unknown",
                        location=location, source="indeed", url=href,
                        remote_type=detect_remote_type(title),
                        job_type=detect_job_type(title),
                    ))
                break
            print(f"[indeed] No cards on page {page + 1}")
            break

        print(f"[indeed] Found {len(cards)} cards")

        for card in cards:
            if len(jobs) >= MAX_JOBS:
                break
            try:
                title_tag = card.select_one("h2 a span, h2 span[title], span[title]")
                if not title_tag:
                    title_tag = card.select_one("h2, h3, a")
                title = title_tag.get_text(strip=True) if title_tag else ""
                if not title:
                    continue

                link_tag = card.select_one("a[data-jk], h2 a, a[href*='viewjob']")
                job_url, data_jk = "", ""
                if link_tag:
                    href = link_tag.get("href", "")
                    if href.startswith("/"):
                        href = "https://de.indeed.com" + href
                    job_url = href
                    data_jk = link_tag.get("data-jk", "")

                company_tag = card.select_one('[data-testid="company-name"], span.companyName, span[class*="company"]')
                company = company_tag.get_text(strip=True) if company_tag else "Unknown"

                loc_tag = card.select_one('[data-testid="text-location"], div.companyLocation, span[class*="location"]')
                job_location = loc_tag.get_text(strip=True) if loc_tag else location

                snippet_tag = card.select_one("div.job-snippet, ul, div[class*='snippet']")
                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                unique_key = data_jk or f"{title}-{company}-{job_location}"
                job_id = make_job_id("indeed", unique_key)
                full_text = f"{title} {snippet} {job_location}"

                jobs.append(build_job_posting(
                    job_id=job_id, title=title, company=company,
                    location=job_location, source="indeed", url=job_url,
                    description_raw=snippet, description_clean=snippet,
                    remote_type=detect_remote_type(full_text),
                    job_type=detect_job_type(full_text),
                ))
            except Exception as e:
                print(f"[indeed] Parse error: {e}")

        time.sleep(2)
    return jobs


def main(query=None, location=None):
    queries = [query] if query else SEARCH_QUERIES
    loc = location or LOCATION
    all_jobs = []
    for q in queries:
        try:
            jobs = scrape_indeed(q, location=loc)
            all_jobs.extend(jobs)
            print(f"[indeed] {q}: {len(jobs)} jobs")
            if len(all_jobs) >= MAX_JOBS:
                break
        except Exception as e:
            print(f"[indeed] Failed on '{q}': {e}")

    if all_jobs:
        seen = {j["id"]: j for j in all_jobs}
        unique_jobs = list(seen.values())[:MAX_JOBS]
        print(f"\n[indeed] Total unique: {len(unique_jobs)}")
        submit_jobs(unique_jobs, "indeed", ", ".join(queries), loc)
    else:
        print("[indeed] No jobs scraped (Indeed blocks plain requests - may need proxy)")


if __name__ == "__main__":
    main()
