"""Run scrapers and submit results to the API.
Usage:
  python run_all.py                                          # run all scrapers sequentially
  python run_all.py --parallel                               # run all scrapers in parallel
  python run_all.py indeed linkedin                          # run specific scrapers
  python run_all.py indeed --parallel                        # run specific scrapers in parallel
  python run_all.py --query "Python Developer" --location "Hessen"  # custom search
  python run_all.py --list                                   # list available scrapers
"""
import sys
import time
import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRAPERS = {
    "indeed": "indeed_scraper",
    "linkedin": "linkedin_scraper",
    "arbeitsagentur": "arbeitsagentur_scraper",
    "stepstone": "stepstone_scraper",
    "xing": "xing_scraper",
}


def run_scraper(name, query=None, location=None):
    module_name = SCRAPERS[name]
    print(f"\n{'='*60}")
    print(f"Running {name} scraper...")
    if query:
        print(f"  Query: {query}")
    if location:
        print(f"  Location: {location}")
    print('='*60)
    start = time.time()
    try:
        module = importlib.import_module(module_name)
        module.main(query=query, location=location)
        elapsed = time.time() - start
        print(f"[{name}] Completed in {elapsed:.1f}s")
        return name, True
    except Exception as e:
        elapsed = time.time() - start
        print(f"[{name}] FAILED after {elapsed:.1f}s: {e}")
        return name, False


def _parse_flag(args_list, flag):
    """Extract --flag value from sys.argv-style list."""
    try:
        idx = args_list.index(flag)
        if idx + 1 < len(args_list):
            return args_list[idx + 1]
    except ValueError:
        pass
    return None


def main():
    parallel = "--parallel" in sys.argv

    if "--list" in sys.argv:
        print("Available scrapers:")
        for name in SCRAPERS:
            print(f"  - {name}")
        return

    query = _parse_flag(sys.argv, "--query")
    location = _parse_flag(sys.argv, "--location")

    skip = set()
    for flag in ["--query", "--location"]:
        try:
            idx = sys.argv.index(flag)
            skip.add(idx)
            skip.add(idx + 1)
        except ValueError:
            pass

    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and i not in skip]
    targets = args if args else list(SCRAPERS.keys())
    for name in targets:
        if name not in SCRAPERS:
            print(f"Unknown scraper: {name}. Available: {', '.join(SCRAPERS.keys())}")
            return

    total_start = time.time()
    results = {}

    if parallel:
        print(f"Running {len(targets)} scrapers in PARALLEL...")
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            futures = {pool.submit(run_scraper, name, query, location): name for name in targets}
            for future in as_completed(futures):
                name, ok = future.result()
                results[name] = ok
    else:
        for name in targets:
            _, ok = run_scraper(name, query, location)
            results[name] = ok

    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE ({total_elapsed:.1f}s) {'[parallel]' if parallel else '[sequential]'}")
    print('='*60)
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
