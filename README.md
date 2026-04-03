# LP–GP Matching System — Vineyard Ventures

Automated LP shortlisting tool. Pulls Vineyard's Notion CRM, extracts structured
investment signals from call notes using AI, and ranks LPs against a specific GP
opportunity using configurable scoring lenses.

## Quick Start

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in CEREBRAS_API_KEY (and NOTION keys if re-scraping)
jupyter notebook lp_shortlist_analysis.ipynb
```

The notebook loads from pre-cached data in `data/` — no API calls needed to view results.

## Pipeline

```
Step 1  fetch_notion_data.py      →  data/raw_lp_data.json
Step 2  extract_signals.py        →  data/lp_signals.json
        lp_shortlist_analysis.ipynb  →  ranked shortlist + visualisations
```

### Re-running from scratch

```bash
python scripts/fetch_notion_data.py   # Step 1: pull LP records from Notion
python scripts/extract_signals.py     # Step 2: AI signal extraction via Cerebras
jupyter notebook lp_shortlist_analysis.ipynb
```

## Files

| File | Description |
|------|-------------|
| `lp_shortlist_analysis.ipynb` | Main deliverable — ranked shortlist, visualisations, sensitivity analysis |
| `writeup.md` | Approach document (submit as PDF) |
| `scripts/fetch_notion_data.py` | Step 1 — fetches LP records from Notion via Playwright → `raw_lp_data.json` |
| `scripts/extract_signals.py` | Step 2 — Cerebras AI extraction of structured signals per LP |
| `data/raw_lp_data.json` | Cached Notion data (13 LP records) |
| `data/lp_signals.json` | Cached AI-extracted signals |
| `.env.example` | Environment variable template |
| `requirements.txt` | Python dependencies |

## Key Design Decisions

- **Notion scraping via Playwright** — the CRM was shared as a public guest page with no
  duplicatable API access, so `fetch_notion_data.py` uses Playwright to navigate each LP page
  and extract structured properties and call notes directly from the DOM.
- **AI for extraction, rules for scoring** — the language model extracts structure from prose;
  deterministic weighted scoring produces auditable, reproducible rankings.
- **Configurable weight lenses** — five scoring presets (Deeptech India, Sector-First,
  Geography-First, Engagement-First, Balanced). Change `DEFAULT_LENS` in the notebook to re-rank.
- **Sensitivity analysis** — the notebook shows how rankings shift across all five lenses;
  LPs that appear in the top 5 under multiple lenses are robust recommendations.
