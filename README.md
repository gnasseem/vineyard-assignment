# LP-GP Matching System — Vineyard Ventures Intern Assignment

Automated LP shortlisting tool for venture fund managers using Notion CRM data and AI signal extraction.

## Setup

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Copy `.env.example` to `.env` and fill in your Cerebras API key:
   ```bash
   cp .env.example .env
   ```

## Data

`data/raw_lp_data.json` — 13 LP records scraped from the Notion CRM — is already committed.
To re-scrape from Notion (e.g. if the CRM is updated), run:
```bash
python scripts/fetch_notion_data.py
```
The CRM is publicly accessible as a guest — no login required.

## Usage

Run the scripts in order (Steps 2-3 enrich and analyse the cached LP data), then open the notebook:

```bash
python scripts/fetch_linkedin.py      # LinkedIn enrichment (best-effort)
python scripts/extract_signals.py     # AI signal extraction via Cerebras
jupyter notebook lp_gp_matching.ipynb # Main deliverable — ranked results
```

The notebook runs entirely from cached data — no API calls needed after the scripts complete.
