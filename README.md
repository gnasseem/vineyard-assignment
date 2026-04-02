# LP-GP Matching System — Vineyard Ventures Intern Assignment

Automated LP shortlisting tool for venture fund managers using Notion CRM data and AI signal extraction.

## Setup

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```

3. Follow the Notion setup instructions in Step 1 of the plan to get your API key and database ID.

## Usage

Run the scripts in order (Steps 1-3 populate the `data/` cache), then open the notebook:

```bash
python scripts/fetch_notion_data.py
python scripts/fetch_linkedin.py
python scripts/extract_signals.py
jupyter notebook lp_gp_matching.ipynb
```

The notebook runs entirely from cached data — no API calls needed after the scripts complete.
