"""
Step 2: LinkedIn Enrichment (Best-Effort)

Reads raw_lp_data.json, attempts to fetch publicly visible data from any
LinkedIn URLs found in each LP record, and writes linkedin_enrichment.json.

── Production note ─────────────────────────────────────────────────────────
This script demonstrates the enrichment pipeline using publicly accessible
profile data. In a production system with 200+ LPs, this step would be
replaced by a paid data provider such as:

  - Proxycurl  (https://nubela.co/proxycurl)  ~$0.01 / profile
  - Piloterr   (https://piloterr.com)         similar pricing
  - PhantomBuster LinkedIn enrichment         $0.03–0.05 / profile

The same JSON output schema is produced regardless of data source,
so the rest of the pipeline (extract_signals.py, notebook) is unchanged.
─────────────────────────────────────────────────────────────────────────────

Output: data/linkedin_enrichment.json
Schema:
  [
    {
      "lp_name": "GEM",
      "linkedin_urls": ["https://linkedin.com/in/..."],
      "profiles": [
        {
          "url": "https://linkedin.com/in/...",
          "name": "John Smith",
          "headline": "Managing Director at GEM Capital",
          "location": "San Francisco, CA",
          "summary": "...",
          "source": "public_scrape" | "proxycurl" | "manual" | "unavailable"
        }
      ]
    }
  ]
"""

import json
import time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────
INPUT_PATH  = Path(__file__).parent.parent / "data" / "raw_lp_data.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "linkedin_enrichment.json"

# Set to True to attempt live scraping (requires playwright install)
# Set to False to run in stub mode — produces empty profiles gracefully
LIVE_SCRAPE = False


def fetch_profile_playwright(url: str) -> dict:
    """Attempt to fetch a public LinkedIn profile via Playwright.

    LinkedIn aggressively blocks automated access. This works for a handful
    of profiles before rate-limiting kicks in. For production use, replace
    with a paid API (see module docstring).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"url": url, "source": "unavailable", "reason": "playwright not installed"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        try:
            page.goto(url, timeout=15000)
            page.wait_for_timeout(3000)

            # Try to extract visible public data
            data = page.evaluate("""
                () => {
                    const name     = document.querySelector('h1')?.textContent?.trim() || '';
                    const headline = document.querySelector('.text-body-medium')?.textContent?.trim() || '';
                    const location = document.querySelector('.text-body-small.inline')?.textContent?.trim() || '';
                    const summary  = document.querySelector('.pv-shared-text-with-see-more span')?.textContent?.trim() || '';
                    return { name, headline, location, summary };
                }
            """)
            data["url"]    = url
            data["source"] = "public_scrape"
            return data

        except Exception as e:
            return {"url": url, "source": "unavailable", "reason": str(e)}
        finally:
            browser.close()


def main():
    with open(INPUT_PATH) as f:
        lps = json.load(f)

    results = []
    total_urls = sum(len(lp.get("linkedin_urls", [])) for lp in lps)
    lps_with_urls = [lp for lp in lps if lp.get("linkedin_urls")]

    print(f"LinkedIn enrichment — {len(lps_with_urls)}/{len(lps)} LPs have URLs ({total_urls} total)")
    print(f"Mode: {'live scraping (Playwright)' if LIVE_SCRAPE else 'stub mode (no requests)'}")
    print()

    if not lps_with_urls:
        print("No LinkedIn URLs found in LP records — nothing to enrich.")
        print("LinkedIn URLs embedded in Notion call notes would appear here.")

    for lp in lps:
        urls = lp.get("linkedin_urls", [])
        profiles = []

        for url in urls:
            print(f"  {lp['name']}: {url}")
            if LIVE_SCRAPE:
                profile = fetch_profile_playwright(url)
                time.sleep(3)  # polite delay between requests
            else:
                # Stub: record the URL but don't fetch
                profile = {
                    "url":    url,
                    "source": "stub",
                    "note":   (
                        "Set LIVE_SCRAPE=True to attempt public scraping, or replace "
                        "this stub with a Proxycurl API call for production use."
                    ),
                }
            profiles.append(profile)

        results.append({
            "lp_name":      lp["name"],
            "linkedin_urls": urls,
            "profiles":     profiles,
        })

    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    enriched = sum(1 for r in results if any(p.get("source") == "public_scrape" for p in r["profiles"]))
    print(f"\nDone. Enrichment data written to {OUTPUT_PATH}")
    print(f"  {enriched} LP(s) enriched via live scraping")
    print(f"  {len(lps_with_urls) - enriched} LP(s) recorded as stubs")
    print(f"\nTo enrich at scale: replace fetch_profile_playwright() with a Proxycurl API call.")


if __name__ == "__main__":
    main()
