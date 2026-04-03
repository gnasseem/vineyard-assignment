"""
Step 1: Fetch LP data from Notion CRM via Playwright browser scraping.

Approach: The Notion CRM is shared as a public guest page — no login required.
We use Playwright to navigate to each LP's page, extract structured properties
and call notes from the DOM, then follow any nested note sub-pages.

NOTE: This script was developed interactively using Claude Code's Playwright MCP,
which navigated each page and used JavaScript evaluation to extract data. The
resulting data is saved to data/raw_lp_data.json. Re-running this script will
re-scrape and overwrite that cache.

Why Playwright over Notion API:
    The shared CRM page was not duplicatable without admin access, so the Notion
    API integration flow (which requires duplicating the page) was not available.
    Playwright scrapes the publicly accessible shared URL directly.

    In a production system with API access, notion-client would be preferable:
    it's faster, more reliable, and handles pagination/rate-limiting natively.

Output: data/raw_lp_data.json
"""

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# ── Config ────────────────────────────────────────────────────────────────────

DATABASE_URL = (
    "https://www.notion.so/9efeca908fc983c08dd4815dafd6eb88"
    "?v=5d6eca908fc9835597708853b2d5d75f"
)
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "raw_lp_data.json"

# LP page IDs discovered via data-block-id attribute scraping on the database view.
# Format: (name, notion_page_id)
LP_PAGES = [
    ("GEM",                         "fa0eca908fc9824ba36d010a40e4873f"),
    ("Everblue Capital Management",  "a3eeca908fc983df9d9701f652b9f6c6"),
    ("Dziugas",                      "5c1eca908fc98292822e8114f3ff437c"),
    ("Charlie Goodacre",             "67beca908fc983dc906681ad0192dde6"),
    ("Weizmann Institute endowment", "d58eca908fc9828d9655810b3e62afcd"),
    ("Mildred Swinton",              "8d1eca908fc982e9862d81b54408a1b9"),
    ("Rezayat",                      "b01eca908fc98309ba5b81dfc54a466b"),
    ("Jordan park",                  "1ebeca908fc983808180014161269aff"),
    ("Ak Asset Management",          "a71eca908fc98214acbb8198709a1bb1"),
    ("UVIMCO",                       "bc0eca908fc982dcbdb9819343e1132d"),
    ("Valence8",                     "e3beca908fc982109b5a818981f12ad1"),
    ("Alber blanc",                  "f83eca908fc982c18c9a011147474754"),
    ("YMCA endowment",               "4ddeca908fc982c19b3e81bec4fdd870"),
]

# ── Extraction helpers ────────────────────────────────────────────────────────

EXTRACT_JS = """
() => {
  const main = document.querySelector('main') || document.body;

  // Title (h1)
  const title = (main.querySelector('h1') || {}).textContent?.trim() || '';

  // Structured properties (table rows in the property panel)
  const props = {};
  main.querySelectorAll('table tr, [role="row"]').forEach(row => {
    const cells = row.querySelectorAll('td, [role="cell"]');
    if (cells.length >= 2) {
      const key = cells[0].textContent.trim();
      const val = cells[1].textContent.trim();
      if (key && val && val !== 'Empty') props[key] = val;
    }
  });

  // Body text via Notion's editable leaf nodes
  const allText = [];
  main.querySelectorAll('[data-content-editable-leaf]').forEach(el => {
    const t = el.textContent.trim();
    if (t) allText.push(t);
  });

  // Links: LinkedIn URLs and nested Notion page links
  const linkedPages = [];
  const linkedinUrls = [];
  main.querySelectorAll('a').forEach(a => {
    const href = a.href || '';
    if (href.includes('linkedin.com')) linkedinUrls.push(href);
    if (href.includes('notion.so') && !href.includes('?v=') && a.textContent.trim()) {
      linkedPages.push({ text: a.textContent.trim(), url: href });
    }
  });

  return {
    title,
    props,
    body_text: allText.join('\\n'),
    linked_pages: linkedPages,
    linkedin_urls: [...new Set(linkedinUrls)],
  };
}
"""

TEXT_ONLY_JS = """
() => {
  const main = document.querySelector('main') || document.body;
  const allText = [];
  main.querySelectorAll('[data-content-editable-leaf]').forEach(el => {
    const t = el.textContent.trim();
    if (t) allText.push(t);
  });
  // Also capture any LinkedIn URLs in nested pages
  const linkedinUrls = [];
  main.querySelectorAll('a').forEach(a => {
    if ((a.href || '').includes('linkedin.com')) linkedinUrls.push(a.href);
  });
  return { text: allText.join('\\n'), linkedin_urls: [...new Set(linkedinUrls)] };
}
"""


def wait_for_notion(page, timeout=10000):
    """Wait until Notion's main content is rendered."""
    page.wait_for_selector('[data-content-editable-leaf], h1', timeout=timeout)


def extract_lp_page(page, name: str, page_id: str) -> dict:
    """Navigate to an LP page and extract all data including nested sub-pages."""
    url = f"https://www.notion.so/{page_id}"
    print(f"  → {name}: {url}")
    page.goto(url)

    try:
        wait_for_notion(page)
    except Exception:
        print(f"    Warning: timeout waiting for content on {name}")
        time.sleep(3)

    data = page.evaluate(EXTRACT_JS)

    # Follow nested Notion page links (e.g. "GEM notes Oct 2025")
    nested_notes = []
    nested_linkedin = []

    for linked in data.get("linked_pages", []):
        nested_url = linked["url"].split("?")[0]  # strip query params
        print(f"    ↳ nested page: {linked['text']}")
        page.goto(nested_url)
        try:
            wait_for_notion(page)
        except Exception:
            time.sleep(3)
        nested_data = page.evaluate(TEXT_ONLY_JS)
        if nested_data["text"]:
            nested_notes.append(
                f"--- {linked['text']} ---\n{nested_data['text']}"
            )
        nested_linkedin.extend(nested_data.get("linkedin_urls", []))
        time.sleep(1)

    # Combine body text + nested page text into call_notes
    parts = []
    if data["body_text"] and data["body_text"].strip() != name:
        # Strip the page title from body_text if Notion included it as first line
        lines = data["body_text"].split("\n")
        body = "\n".join(l for l in lines if l.strip() != name)
        if body.strip():
            parts.append(body)
    parts.extend(nested_notes)
    call_notes = "\n\n".join(parts)

    all_linkedin = list(set(data["linkedin_urls"] + nested_linkedin))

    return {
        "id": page_id,
        "name": name,
        "notion_url": f"https://www.notion.so/{page_id}",
        "structured_fields": data["props"],
        "call_notes": call_notes,
        "linkedin_urls": all_linkedin,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # Launch in non-headless mode so user can log in if required.
        # The Notion pages are publicly shared as guest, so login is typically
        # not needed — but if a login wall appears, handle it manually.
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print(f"Navigating to database: {DATABASE_URL}")
        page.goto(DATABASE_URL)
        time.sleep(3)  # let Notion load

        # ── If you see a login prompt, log in now. ──
        # The script will wait 30s to give you time before proceeding.
        # In practice the shared guest page doesn't require login.
        # If it does, uncomment the line below:
        # input("Press Enter after logging in...")

        lps = []
        for name, page_id in LP_PAGES:
            lp = extract_lp_page(page, name, page_id)
            lps.append(lp)
            time.sleep(1.5)  # polite delay between pages

        browser.close()

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(lps, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Saved {len(lps)} LP records to {OUTPUT_PATH}")
    with_notes = sum(1 for lp in lps if lp["call_notes"].strip())
    with_linkedin = sum(1 for lp in lps if lp["linkedin_urls"])
    print(f"  {with_notes}/{len(lps)} LPs have call notes")
    print(f"  {with_linkedin}/{len(lps)} LPs have LinkedIn URLs")


if __name__ == "__main__":
    main()
