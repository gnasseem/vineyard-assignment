"""
Step 1: Fetch LP data from Notion CRM.

Connects to the Notion API, queries the LP database, and recursively
extracts structured fields + call notes from nested page blocks.
Output: data/raw_lp_data.json
"""

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "raw_lp_data.json"


def get_plain_text(rich_text_list: list) -> str:
    """Extract plain text from a Notion rich_text array."""
    return "".join(item.get("plain_text", "") for item in rich_text_list)


def extract_property(prop: dict) -> str | list | None:
    """Extract a human-readable value from any Notion property object."""
    ptype = prop.get("type")
    if ptype == "title":
        return get_plain_text(prop["title"])
    elif ptype == "rich_text":
        return get_plain_text(prop["rich_text"])
    elif ptype == "select":
        sel = prop.get("select")
        return sel["name"] if sel else None
    elif ptype == "multi_select":
        return [item["name"] for item in prop.get("multi_select", [])]
    elif ptype == "url":
        return prop.get("url")
    elif ptype == "email":
        return prop.get("email")
    elif ptype == "phone_number":
        return prop.get("phone_number")
    elif ptype == "number":
        return prop.get("number")
    elif ptype == "checkbox":
        return prop.get("checkbox")
    elif ptype == "date":
        date = prop.get("date")
        return date["start"] if date else None
    elif ptype == "people":
        return [p.get("name") for p in prop.get("people", [])]
    elif ptype == "files":
        return [f.get("name") for f in prop.get("files", [])]
    elif ptype == "relation":
        return [r["id"] for r in prop.get("relation", [])]
    elif ptype == "formula":
        formula = prop.get("formula", {})
        ftype = formula.get("type")
        return formula.get(ftype)
    elif ptype == "status":
        status = prop.get("status")
        return status["name"] if status else None
    return None


def extract_blocks_text(notion: Client, block_id: str, depth: int = 0) -> tuple[str, list[str]]:
    """
    Recursively extract text content and LinkedIn URLs from all blocks under block_id.
    Returns (text_content, linkedin_urls).
    """
    text_parts = []
    linkedin_urls = []

    try:
        response = notion.blocks.children.list(block_id=block_id)
    except Exception as e:
        print(f"  Warning: could not fetch blocks for {block_id}: {e}")
        return "", []

    for block in response.get("results", []):
        btype = block.get("type", "")
        block_data = block.get(btype, {})

        # Extract rich text from common block types
        rich_text = block_data.get("rich_text", [])
        if rich_text:
            line = get_plain_text(rich_text)
            if line.strip():
                indent = "  " * depth
                text_parts.append(f"{indent}{line}")

            # Scan for LinkedIn URLs in rich text annotations/links
            for rt in rich_text:
                href = rt.get("href") or (rt.get("text", {}) or {}).get("link", {}) or {}
                if isinstance(href, dict):
                    href = href.get("url", "")
                if href and "linkedin.com" in str(href):
                    linkedin_urls.append(href)

        # Handle URL blocks (bookmarks, embeds)
        if btype in ("bookmark", "embed", "link_preview"):
            url = block_data.get("url", "")
            if url and "linkedin.com" in url:
                linkedin_urls.append(url)

        # Recurse into child blocks
        if block.get("has_children"):
            child_text, child_links = extract_blocks_text(notion, block["id"], depth + 1)
            if child_text:
                text_parts.append(child_text)
            linkedin_urls.extend(child_links)

    return "\n".join(text_parts), linkedin_urls


def fetch_all_lps(notion: Client) -> list[dict]:
    """Query all LP records from the database, handling pagination."""
    results = []
    cursor = None

    while True:
        kwargs = {"database_id": NOTION_DATABASE_ID}
        if cursor:
            kwargs["start_cursor"] = cursor

        response = notion.databases.query(**kwargs)
        results.extend(response.get("results", []))

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return results


def process_lp(notion: Client, page: dict) -> dict:
    """Extract all fields from a single LP page record."""
    page_id = page["id"]
    properties = page.get("properties", {})

    # Extract all structured properties
    structured = {}
    for prop_name, prop_value in properties.items():
        value = extract_property(prop_value)
        if value is not None:
            structured[prop_name] = value

    # Determine LP name (title property, whatever it's called)
    name = None
    for prop_name, prop_value in properties.items():
        if prop_value.get("type") == "title":
            name = get_plain_text(prop_value["title"])
            break

    # Extract call notes and LinkedIn URLs from nested blocks
    print(f"  Fetching blocks for: {name or page_id}")
    call_notes, linkedin_urls = extract_blocks_text(notion, page_id)

    return {
        "id": page_id,
        "name": name,
        "call_notes": call_notes,
        "linkedin_urls": list(set(linkedin_urls)),  # deduplicate
        "structured_fields": structured,
        "notion_url": page.get("url"),
    }


def main():
    if not NOTION_API_KEY:
        raise ValueError("NOTION_API_KEY not set in .env")
    if not NOTION_DATABASE_ID:
        raise ValueError("NOTION_DATABASE_ID not set in .env")

    notion = Client(auth=NOTION_API_KEY)

    print("Fetching LP records from Notion database...")
    pages = fetch_all_lps(notion)
    print(f"Found {len(pages)} LP records")

    lps = []
    for i, page in enumerate(pages):
        print(f"\n[{i+1}/{len(pages)}] Processing LP...")
        lp = process_lp(notion, page)
        lps.append(lp)
        # Respect Notion API rate limits (3 req/s)
        time.sleep(0.4)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(lps, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Saved {len(lps)} LP records to {OUTPUT_PATH}")

    # Quick summary
    with_notes = sum(1 for lp in lps if lp["call_notes"].strip())
    with_linkedin = sum(1 for lp in lps if lp["linkedin_urls"])
    print(f"  {with_notes}/{len(lps)} LPs have call notes")
    print(f"  {with_linkedin}/{len(lps)} LPs have LinkedIn URLs")


if __name__ == "__main__":
    main()
