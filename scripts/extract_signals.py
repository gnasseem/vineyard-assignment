"""
Step 3: AI Signal Extraction

Reads raw_lp_data.json, calls Cerebras (Qwen 3 235B) to extract structured
investment signals from each LP's call notes, and writes lp_signals.json.

Each LP's call notes are passed through a structured-output prompt that maps
free-form prose to a Pydantic schema (LPSignals).  The model is instructed to
score dimensions on 0–10 scales and base every rating on explicit evidence —
no invented signals.

Supports incremental re-runs: if lp_signals.json already exists, only LPs
not yet processed are sent to the API.  Results are persisted after every LP
so a partial run is never lost.

GP context: Vineyard Ventures — $20M fund, pre-seed/seed, Indian deeptech
(AI, hardware, defence, bio).
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

# ---------------------------------------------------------------------------
# Pydantic schema for structured extraction
# ---------------------------------------------------------------------------

class LPSignals(BaseModel):
    # LP profile
    lp_type: str  # endowment | family_office | OCIO | wealth_manager | individual | other
    aum_estimate: Optional[str]  # e.g. "$10B", "$500M", "unknown"
    typical_check_size: Optional[str]  # e.g. "$5-10M", "$20-30M", "unknown"

    # Geographic fit
    india_interest: int       # 0-10: 0 = none/negative, 5 = open/neutral, 10 = actively seeking India
    india_interest_rationale: str  # one sentence evidence from notes

    # Fund size & stage fit
    preferred_fund_size: Optional[str]      # e.g. "sub-100M", "$200-500M", "unknown"
    preferred_stages: list[str]             # pre-seed | seed | series-a | growth
    emerging_manager_preference: bool       # explicitly prefers emerging/first-time GPs

    # Sector fit
    deeptech_interest: bool    # AI, hardware, defence, bio, frontier tech
    sector_agnostic: bool      # willing to invest regardless of sector
    sectors_mentioned: list[str]  # verbatim sectors from notes

    # FoF fit
    fof_experience: bool       # has invested in funds-of-funds before
    fof_openness: int          # 0-10: 0 = no interest, 5 = open, 10 = actively seeking FoF

    # Relationship & engagement
    engagement_level: int      # 0-10: 0 = cold/passed, 5 = warm, 10 = near-commit
    blockers: list[str]        # reasons they might not invest
    positives: list[str]       # reasons they are a good fit

    # Overall fit assessment
    fit_score: int             # 0-10 vs this specific GP opportunity
    fit_rationale: str         # 2-3 sentence narrative tying signals to GP


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert venture capital analyst helping assess LP-GP fit.

You will be given raw call notes about a Limited Partner (LP).
Extract structured investment signals relevant to matching this LP against a specific GP opportunity.

GP OPPORTUNITY CONTEXT:
- Fund: Vineyard Ventures
- Fund size: ~$20M (very small / emerging fund)
- Strategy: Fund-of-Funds (FoF) investing in GPs — not direct company investments
- Focus: Pre-seed and seed stage
- Geography: Indian deeptech — AI, hardware, defence, biotech
- Team: Young, London-based, emerging GP (Fund 1)

Extract signals carefully. If information is absent or ambiguous, use "unknown" or conservative estimates.
Base every rating on explicit evidence in the notes — do not invent signals.
Use 0-10 scales for all integer fields (india_interest, fof_openness, engagement_level, fit_score).
Return valid JSON matching the schema exactly."""

USER_PROMPT_TEMPLATE = """LP NAME: {name}
STRUCTURED CRM FIELDS: {structured_fields}

CALL NOTES:
{call_notes}

Extract the investment signals for this LP."""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_client() -> OpenAI:
    api_key = os.getenv("CEREBRAS_API_KEY")
    if not api_key:
        raise EnvironmentError("CEREBRAS_API_KEY not set in environment")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.cerebras.ai/v1",
    )


def extract_signals_for_lp(client: OpenAI, lp: dict) -> dict:
    call_notes = lp.get("call_notes", "").strip()
    if not call_notes:
        print(f"  [skip] {lp['name']} — no call notes")
        return {}

    user_prompt = USER_PROMPT_TEMPLATE.format(
        name=lp["name"],
        structured_fields=json.dumps(lp.get("structured_fields", {})),
        call_notes=call_notes,
    )

    response = client.beta.chat.completions.parse(
        model="qwen-3-235b-a22b-instruct-2507",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format=LPSignals,
        temperature=0.1,
    )

    signals = response.choices[0].message.parsed
    return signals.model_dump()


def main():
    data_dir = Path(__file__).parent.parent / "data"
    raw_path = data_dir / "raw_lp_data.json"
    output_path = data_dir / "lp_signals.json"

    with open(raw_path) as f:
        lps = json.load(f)

    # Load existing results to allow incremental re-runs
    if output_path.exists():
        with open(output_path) as f:
            existing = {r["id"]: r for r in json.load(f)}
        print(f"Resuming — {len(existing)} LP(s) already processed")
    else:
        existing = {}

    client = build_client()
    results = list(existing.values())
    already_done = set(existing.keys())

    for i, lp in enumerate(lps):
        lp_id = lp["id"]
        if lp_id in already_done:
            print(f"[{i+1}/{len(lps)}] {lp['name']} — already done, skipping")
            continue

        print(f"[{i+1}/{len(lps)}] Extracting signals for: {lp['name']} ...", end=" ", flush=True)

        try:
            signals = extract_signals_for_lp(client, lp)
            if signals:
                results.append({
                    "id": lp_id,
                    "name": lp["name"],
                    "notion_url": lp.get("notion_url", ""),
                    "structured_fields": lp.get("structured_fields", {}),
                    "linkedin_urls": lp.get("linkedin_urls", []),
                    "signals": signals,
                })
                print(f"fit_score={signals['fit_score']}/10")
            else:
                print("skipped")
        except Exception as e:
            print(f"ERROR: {e}")

        # Persist after every LP so partial runs are not lost
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        # Respect rate limit: 30 req/min = 1 req every 2s (conservative)
        if i < len(lps) - 1:
            time.sleep(2)

    print(f"\nDone. {len(results)} LP(s) written to {output_path}")


if __name__ == "__main__":
    main()
