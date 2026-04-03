# LP–GP Matching System — Approach & Write-Up

**Vineyard Ventures Intern Assignment**
George Nasseem | April 2026

---

## 1. Problem Decomposition

Before writing a single line of code, I broke the problem into three distinct sub-problems:

**Sub-problem 1 — Data access.** The most important LP signals are buried in Notion call notes stored as embedded sub-pages, not flat text fields. These are not queryable via Notion's built-in filters. The first challenge was extracting this content programmatically — at a scale that would work for 200 LPs, not just 15.

**Sub-problem 2 — Signal extraction.** Even once extracted, the notes are free-form prose. One note might say "they've done a lot of India-focused funds"; another might say "not interested in geographies they haven't travelled to." Both convey geographic preference, but no regex or keyword search would reliably catch both. This is a job for a language model.

**Sub-problem 3 — Matching and ranking.** Given structured signals for each LP, how do you rank them against a *specific* GP opportunity? The criteria differ by fund type — what matters most for an Indian deeptech fund is different from what matters for a European climate fund. The scoring system needed to be configurable, not hardcoded.

I deliberately separated these three problems. Conflating them (e.g. asking an LLM to "score this LP for this GP in one shot") produces a black box that is hard to debug, impossible to audit, and breaks when the GP profile changes.

---

## 2. Data Parsing Approach

### Why Playwright, not the Notion API

My first instinct was to use the official Notion API (`notion-client`). It is the correct production choice: structured JSON output, handles nested pages natively, scales to thousands of records. However, the official API requires the page owner to create an integration and explicitly grant access — it does not work on shared guest pages without workspace-level setup.

Since I was working with a publicly shared guest link and could not create an integration on Vineyard's workspace, I used **Playwright** browser automation instead. Playwright renders the page as a real browser would, then extracts data via JavaScript evaluation. This is slower and more fragile than the API, but it works on any publicly accessible Notion URL without authentication setup.

The scraping code (`scripts/fetch_notion_data.py`) does the following:
- Navigates to each LP's Notion page
- Extracts structured properties from the page's property panel
- Follows any nested page links (e.g. "GEM notes Oct 2025") to retrieve embedded call notes
- Collects any LinkedIn URLs found in the page content
- Saves everything to `data/raw_lp_data.json`

This data is committed to the repo. The notebook loads from this cache, so no re-scraping is needed during a demo or review.

**In a production system:** the Notion API would replace Playwright entirely. The same JSON schema would be produced, and the rest of the pipeline would be unchanged. The scraping approach was a pragmatic adaptation to the constraints of a shared guest page.

### Note Structure

Each LP record is stored as:
```json
{
  "id": "page-id",
  "name": "LP Name",
  "structured_fields": { "Status": "...", "Location": "...", ... },
  "call_notes": "Full text of all nested call note blocks...",
  "linkedin_urls": ["https://linkedin.com/in/..."]
}
```

---

## 3. Fit Criteria and Weighting

### The six dimensions

After reading the LP records and the GP opportunity brief, I identified six dimensions that determine LP–GP fit for this specific fund:

| Dimension | Why It Matters for This GP |
|-----------|---------------------------|
| **Fit Score** (AI holistic) | Anchors the composite; captures nuance the other five dimensions might miss |
| **India Interest** | Hard filter — an LP with no India/EM exposure is unlikely to back an India-only fund |
| **FoF Openness** | The GP is a fund vehicle; LP must be willing to invest via funds, not just direct |
| **Engagement Level** | Warm LPs close faster; cold LPs require months of education |
| **Emerging Manager Preference** | First-time fund is the hardest sell; LPs with existing emerging-manager mandates skip the hardest objection |
| **Deeptech Interest** | Nice-to-have; shared sector vocabulary reduces diligence friction |

### Configurable weight lenses

Rather than a single hardcoded formula, I built a **lens system** with five presets:

- **Deeptech India (default):** Sector + geography both at 25% — both are hard filters for this fund
- **Sector-First:** For niche funds where thematic alignment matters most
- **Geography-First:** For EM funds where the geography is the primary differentiator
- **Engagement-First:** For pipeline velocity — surface the most actionable LPs right now
- **Balanced:** Equal weighting — for generalist funds with no dominant filter

The notebook's sensitivity analysis shows how the top-5 ranking shifts across lenses. An LP that appears in the top 5 under *every* lens is a high-confidence recommendation; one that only appears under the deeptech lens is a more conditional pick.

### What I explicitly excluded

The Notion `Status` field (In Diligence, Qualified, Nurture) was *not* used as a scoring input. Per the assignment brief, this field reflects the LP's relationship with Vineyard's *own* fundraise, not their suitability for any given GP opportunity. Using it would conflate two different signals and bias the ranking toward LPs that Vineyard is already actively pitching on its own behalf.

---

## 4. AI vs Rules-Based Decisions

The pipeline uses both AI and rules-based logic. The boundary was drawn deliberately:

### AI: signal extraction from unstructured text

The call notes are free-form prose written by different people over time, with no consistent structure. Extracting signals like "has this LP ever backed an India fund?" or "do they prefer sub-$50M fund sizes?" from this text is exactly where language models outperform rules-based approaches. A regex-based system would miss synonyms, paraphrasing, and implicit signals.

I used **Cerebras / Qwen 3 235B** for this step. The model is given structured call notes and a detailed system prompt with the GP context, and it returns a structured JSON object (validated against a Pydantic schema) with 14 signal fields per LP. The extraction runs once, results are cached, and the notebook never re-calls the API during a demo.

### Rules-based: scoring and ranking

Once signals are structured, I deliberately switched to rules-based scoring. The composite score is a weighted sum of numeric signal dimensions — entirely deterministic and transparent. You can see exactly why LP #1 outranks LP #2, trace back which signals drove the difference, and adjust the weights to test different hypotheses.

Asking an LLM to "rate this LP 1-10 for this GP" produces inconsistent results across runs, is impossible to audit, and changes unpredictably when the GP description changes slightly. For a ranking system that needs to be trusted and debugged, rules-based scoring is the right tool.

### AI: explanation generation (optional)

The `fit_rationale` field in each LP profile is generated by the same LLM during the extraction pass. This is appropriate because writing a narrative explanation of a fit judgment is exactly what language models are good at — it requires synthesis, not consistency.

---

## 5. Tools Considered and Rejected

**Manual CSV export from Notion** — rejected. Notion's CSV export flattens the data and loses all call note content (which lives in sub-pages). A manually exported CSV would miss the single most important data source. More importantly, it doesn't scale: a new export would be needed every time the CRM is updated.

**Notion official API** — considered, practically unavailable. The API requires workspace admin access to create an integration. As a guest user, I cannot set this up on Vineyard's workspace. In a production deployment (or if given API access), this would replace the Playwright approach entirely.

**LLM-as-judge scoring** — rejected. Asking the model to score LPs directly (rather than extract signals and then apply rules) produces a black box that cannot be audited, compared, or tuned. Interviewers and fund managers can't see why one LP scored higher than another.

**Vector embeddings / semantic search** — considered, over-engineered for this dataset. With 15 LPs, cosine similarity between LP notes and a GP description would work, but it would be harder to explain, harder to debug, and no more accurate than a well-designed scoring rubric. Embeddings become compelling at 1000+ LPs where you need fast approximate search — not here.

**Proxycurl / paid LinkedIn API** — considered for enrichment, deferred. At ~$0.01/profile, the cost is trivial at scale. The `scripts/fetch_linkedin.py` script demonstrates the full enrichment pipeline and includes the schema that a Proxycurl integration would populate. For the prototype, LinkedIn is supplementary — the call notes are the primary signal source.

---

## 6. Tradeoffs and Future Vision

### Tradeoffs made for this prototype

- **Signal extraction is AI-scored, not rules-scored.** The `india_interest`, `fof_openness`, and `engagement_level` fields are rated 0–10 by the language model, not by a rules-based classifier. This is a pragmatic compromise: building rules to reliably quantify these from raw text would take much longer than this assignment allows. The model's ratings are well-calibrated for this dataset, but a production system should replace the numeric ratings with extractive facts (e.g. "has backed India funds: true/false, evidence: [quote]") that a rules layer then scores.

- **No feedback loop.** The system has no way to learn from Vineyard's actual outreach outcomes. In production, tracking which recommended LPs actually committed (and which didn't) would let us calibrate the weights empirically rather than by judgment.

- **Playwright scraping is fragile.** Notion's frontend changes occasionally break scraping. The Notion API would fix this but requires access that wasn't available here.

### What a purpose-built LP CRM should look like

Vineyard mentioned that Notion is not the right tool for this workflow — and the limitations are obvious from building this system. The core problem is that **the most valuable data (call notes) is the hardest to query**.

A purpose-built LP CRM for a fund-of-funds would:

1. **Structured call note intake.** Each call note is written against a template that captures key fields (sectors mentioned, geography signals, check size range, stage preference, emerging-manager stance). Free text is still supported, but the template primes the note-taker to capture the signals that matter.

2. **Automatic signal extraction on save.** Every time a call note is saved, run the same extraction pipeline used here. The structured signals are stored alongside the note and kept current.

3. **GP-aware matching.** When a new GP opportunity is added, the system automatically re-ranks all LPs using the configurable lens system, presents a ranked shortlist, and surfaces the most relevant quotes from call notes as supporting evidence.

4. **Outcome tracking.** Record whether an LP was approached, whether they took a meeting, and whether they committed. Over time, use this to learn which signals are actually predictive — not just which ones seem plausible.

5. **CRM integration.** Rather than building from scratch, the matching engine developed here could be layered on top of an existing CRM (Affinity, HubSpot, Airtable) via API, providing the intelligent matching layer without replacing the relationship management tooling the team already uses.

The prototype built for this assignment is the matching engine at the core of this system. The scripts, the Pydantic schema, and the notebook are all designed to be modular enough to plug into a production pipeline with minimal rework.

---

*Code is available at: [GitHub repository link]*
*Contact: georgenasseem@[email]*
