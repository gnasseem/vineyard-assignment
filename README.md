# LP–GP Matching System — Vineyard Ventures

Scores Vineyard's LP CRM against a specific GP opportunity and produces a ranked shortlist with outreach recommendations.

---

## For reviewers — just open the notebook

All data is pre-cached. No API keys or scraping needed.

```bash
pip install -r requirements.txt
jupyter notebook lp_shortlist_analysis.ipynb
```

Run all cells top to bottom. The notebook loads from `data/lp_signals.json` and `data/raw_lp_data.json` — both already present in the repo.

**To change the scoring lens** (e.g. prioritise geography over sector): edit `DEFAULT_LENS` in Cell 1 and re-run. Options: `deeptech_india` (default), `sector_first`, `geography_first`, `engagement_first`, `balanced`.

---

## Files

| File | What it is |
|------|-----------|
| `lp_shortlist_analysis.ipynb` | Main deliverable — ranked shortlist, charts, sensitivity analysis, outreach plan |
| `writeup.md` | Approach document (submitted as PDF) |
| `data/lp_signals.json` | Pre-extracted LP signals (13 LPs, 14 fields each) |
| `data/raw_lp_data.json` | Raw Notion data including full call notes |
| `scripts/fetch_notion_data.py` | Step 1 — scrapes LP records from Notion via Playwright |
| `scripts/extract_signals.py` | Step 2 — AI signal extraction via Cerebras |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |

---

## Re-running the pipeline from scratch

The two scripts are only needed if you want to re-scrape Notion or re-extract signals. This requires API credentials and is not needed to view results.

```bash
cp .env.example .env          # add CEREBRAS_API_KEY
playwright install chromium   # one-time browser install (~150 MB)

python scripts/fetch_notion_data.py   # scrape Notion → data/raw_lp_data.json
python scripts/extract_signals.py     # AI extraction → data/lp_signals.json
jupyter notebook lp_shortlist_analysis.ipynb
```

`extract_signals.py` is incremental — it skips LPs already in `lp_signals.json`, so partial runs are safe.

---

## Design decisions

- **Playwright over Notion API** — the CRM was shared as a public guest link with no API access. Production swap: replace `fetch_notion_data.py` with Notion API calls; everything downstream stays the same.
- **AI for extraction, rules for scoring** — LLM handles synonyms and implicit signals in free-text notes; deterministic weighted scoring produces auditable, reproducible rankings.
- **Configurable lenses** — five weight presets so the same pipeline re-ranks correctly for a different fund type (e.g. geography-first vs sector-first).
- **Sensitivity analysis** — ranks each LP under all five lenses; an LP that stays top-5 across every lens is a high-confidence pick.
