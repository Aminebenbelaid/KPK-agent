"""Xing jobs scraper using pure Playwright."""
from playwright.sync_api import sync_playwright
from base import make_job_id, build_job_posting, submit_jobs, detect_remote_type, detect_job_type
from base_playwright import new_context

SEARCH_QUERIES = ["Software Entwickler", "Python Developer", "Webentwickler", "Frontend Entwickler"]
LOCATION = "Nordrhein-Westfalen"
MAX_PAGES = 3
MAX_JOBS = 10


def scrape_xing(query, location=LOCATION, max_pages=MAX_PAGES):
    jobs = []
    encoded_q = query.replace(" ", "%20")
    encoded_l = location.replace(" ", "%20")

    with sync_playwright() as p:
        browser, context = new_context(p)
        page = context.new_page()

        for pg in range(max_pages):
            if len(jobs) >= MAX_JOBS:
                break
            url = f"https://www.xing.com/jobs/search?keywords={encoded_q}&location={encoded_l}&page={pg+1}"
            print(f"[xing-pw] Scraping: {query} - page {pg + 1}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                for sel in ['button[data-testid="consent-accept-button"]', "button#consent-accept-button"]:
                    try:
                        page.click(sel, timeout=1500)
                        break
                    except Exception:
                        pass
                for _ in range(5):
                    page.mouse.wheel(0, 600)
                    page.wait_for_timeout(250)

                cards = page.query_selector_all('article[data-testid="job-search-result"], div[class*="JobSearchResult"]')
                if not cards:
                    print(f"[xing-pw] No cards on page {pg + 1}, trying links")
                    links = page.query_selector_all('a[href*="/jobs/"]')
                    seen_urls = set()
                    for link in links:
                        if len(jobs) >= MAX_JOBS:
                            break
                        href = link.get_attribute("href") or ""
                        if href in seen_urls or "search" in href:
                            continue
                        seen_urls.add(href)
                        title = link.inner_text().strip()
                        if not title or len(title) < 5:
                            continue
                        job_url = "https://www.xing.com" + href if href.startswith("/") else href
                        job_id = make_job_id("xing-pw", job_url)
                        jobs.append(build_job_posting(
                            job_id=job_id, title=title, company="Unknown",
                            location=location, source="xing-playwright", url=job_url,
                            remote_type=detect_remote_type(title), job_type=detect_job_type(title),
                        ))
                    break

                print(f"[xing-pw] Found {len(cards)} cards")
                for card in cards:
                    if len(jobs) >= MAX_JOBS:
                        break
                    try:
                        title_el = card.query_selector('h2, h3, a[class*="title"]')
                        title = title_el.inner_text().strip() if title_el else ""
                        if not title:
                            continue
                        link_el = card.query_selector('a[href*="/jobs/"]')
                        job_url = ""
                        if link_el:
                            href = link_el.get_attribute("href") or ""
                            job_url = "https://www.xing.com" + href if href.startswith("/") else href
                        company_el = card.query_selector('[class*="company"], [data-testid="company"]')
                        company = company_el.inner_text().strip() if company_el else "Unknown"
                        loc_el = card.query_selector('[class*="location"], [data-testid="location"]')
                        job_location = loc_el.inner_text().strip() if loc_el else location
                        unique_key = job_url or f"{title}-{company}"
                        job_id = make_job_id("xing-pw", unique_key)
                        full_text = f"{title} {job_location}"
                        jobs.append(build_job_posting(
                            job_id=job_id, title=title, company=company,
                            location=job_location, source="xing-playwright", url=job_url,
                            remote_type=detect_remote_type(full_text), job_type=detect_job_type(full_text),
                        ))
                    except Exception as e:
                        print(f"[xing-pw] Card error: {e}")
            except Exception as e:
                print(f"[xing-pw] Page error: {e}")
                break
        browser.close()
    return jobs


def main():
    all_jobs = []
    for query in SEARCH_QUERIES:
        try:
            jobs = scrape_xing(query)
            all_jobs.extend(jobs)
            print(f"[xing-pw] {query}: {len(jobs)} jobs")
            if len(all_jobs) >= MAX_JOBS:
                break
        except Exception as e:
            print(f"[xing-pw] Failed on '{query}': {e}")
    if all_jobs:
        seen = {j["id"]: j for j in all_jobs}
        unique_jobs = list(seen.values())[:MAX_JOBS]
        print(f"\n[xing-pw] Total unique: {len(unique_jobs)}")
        submit_jobs(unique_jobs, "xing-playwright", ", ".join(SEARCH_QUERIES), LOCATION)
    else:
        print("[xing-pw] No jobs scraped")

if __name__ == "__main__":
    main()
