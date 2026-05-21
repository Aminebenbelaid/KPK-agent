"""Agentur fuer Arbeit scraper using pure Playwright."""
from playwright.sync_api import sync_playwright
from base import make_job_id, build_job_posting, submit_jobs, detect_remote_type, detect_job_type
from base_playwright import new_context

SEARCH_QUERIES = ["Softwareentwickler", "Webentwickler", "Python Entwickler", "IT Junior"]
LOCATION = "Nordrhein-Westfalen"
MAX_PAGES = 3
MAX_JOBS = 10


def scrape_arbeitsagentur(query, location=LOCATION, max_pages=MAX_PAGES):
    jobs = []
    encoded_q = query.replace(" ", "%20")

    with sync_playwright() as p:
        browser, context = new_context(p)
        page = context.new_page()

        for pg in range(max_pages):
            if len(jobs) >= MAX_JOBS:
                break
            url = (
                f"https://www.arbeitsagentur.de/jobsuche/suche"
                f"?was={encoded_q}&wo={location.replace(' ', '%20')}"
                f"&seite={pg+1}&veroeffentlichtseit=7"
            )
            print(f"[arbeitsagentur-pw] Scraping: {query} - page {pg + 1}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(3000)
                for sel in ['button[data-testid="cookie-accept-all"]', "button.ba-btn--primary"]:
                    try:
                        page.click(sel, timeout=1500)
                        break
                    except Exception:
                        pass
                page.wait_for_timeout(1500)
                for _ in range(4):
                    page.mouse.wheel(0, 500)
                    page.wait_for_timeout(300)

                cards = page.query_selector_all('[class*="ergebnis"], article, [data-testid="jobcard"]')
                cards = [c for c in cards if c.query_selector("h2, h3, a")]
                if not cards:
                    print(f"[arbeitsagentur-pw] No cards on page {pg + 1}")
                    break
                print(f"[arbeitsagentur-pw] Found {len(cards)} cards")

                for card in cards:
                    if len(jobs) >= MAX_JOBS:
                        break
                    try:
                        title_el = card.query_selector("h2, h3")
                        title = title_el.inner_text().strip() if title_el else ""
                        if not title or len(title) < 3:
                            continue
                        link_el = card.query_selector("a[href]")
                        job_url = ""
                        if link_el:
                            href = link_el.get_attribute("href") or ""
                            job_url = "https://www.arbeitsagentur.de" + href if href.startswith("/") else href
                        company = "Unknown"
                        job_location = location
                        for span in card.query_selector_all("span, p"):
                            text = span.inner_text().strip()
                            if any(w in text.lower() for w in ["gmbh", "ag", "e.v.", "kg"]):
                                company = text
                            elif any(w in text.lower() for w in ["nordrhein", "nrw", "koeln", "duesseldorf", "essen", "dortmund"]):
                                job_location = text
                        unique_key = job_url or f"{title}-{company}"
                        job_id = make_job_id("arbeitsagentur-pw", unique_key)
                        full_text = f"{title} {job_location}"
                        jobs.append(build_job_posting(
                            job_id=job_id, title=title, company=company,
                            location=job_location, source="arbeitsagentur-playwright", url=job_url,
                            remote_type=detect_remote_type(full_text), job_type=detect_job_type(full_text),
                        ))
                    except Exception as e:
                        print(f"[arbeitsagentur-pw] Card error: {e}")
            except Exception as e:
                print(f"[arbeitsagentur-pw] Page error: {e}")
                break
        browser.close()
    return jobs


def main():
    all_jobs = []
    for query in SEARCH_QUERIES:
        try:
            jobs = scrape_arbeitsagentur(query)
            all_jobs.extend(jobs)
            print(f"[arbeitsagentur-pw] {query}: {len(jobs)} jobs")
            if len(all_jobs) >= MAX_JOBS:
                break
        except Exception as e:
            print(f"[arbeitsagentur-pw] Failed on '{query}': {e}")
    if all_jobs:
        seen = {j["id"]: j for j in all_jobs}
        unique_jobs = list(seen.values())[:MAX_JOBS]
        print(f"\n[arbeitsagentur-pw] Total unique: {len(unique_jobs)}")
        submit_jobs(unique_jobs, "arbeitsagentur-playwright", ", ".join(SEARCH_QUERIES), LOCATION)
    else:
        print("[arbeitsagentur-pw] No jobs scraped")

if __name__ == "__main__":
    main()
