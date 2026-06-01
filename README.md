# London Office CRE Monitoring AI Agent

A runnable Python PoC for monitoring the London office market with explainable
signals, alerts, and weekly business reporting.

This project was built for the Nan Fung technical assessment and is designed to
be easy to run, audit, and extend.

## What It Does

- Ingests market data (macro + news + CRE sample set)
- Normalizes and tags every row with data provenance and quality
- Computes submarket-level composite scores
- Raises early-warning alerts with evidence and severity controls
- Answers business questions with traceable evidence
- Generates a weekly briefing in Markdown

Pipeline:

```text
ingest -> normalize -> analysis -> news_impact -> alert -> qa -> report
```

## Business Coverage

The agent tracks the dimensions requested in the test brief:

- Prime and Grade A rents
- Vacancy and availability
- Leasing take-up and net absorption
- Supply pipeline (new, completions, refurbishments, pre-lets)
- Submarket dynamics (City, West End, Canary Wharf, Midtown)
- Macro context (rates, CPI/core CPI, unemployment, gilt yield, employment proxy)
- Occupier demand drivers (hybrid, ESG, flight-to-quality, tenant moves, financing)
- Emerging news/events and forward watchlist

## Data Integrity (Non-Negotiable)

Every row is explicitly tagged as:

- `observed` (live source with provenance)
- `estimated` (derived / incomplete provenance)
- `synthetic` (sample or fallback)

No synthetic value is presented as a real market fact.

See `DATA_INTEGRITY.md` for full policy and enforcement rules.

## Quick Start

### Option A — Zero-config run (recommended for first review)

No API keys required. The agent runs the full workflow on the bundled
`sample_data/` and produces a real weekly briefing.

```bash
# 1) Install deps
pip install -r requirements.txt

# 2) Run the full workflow and generate the weekly briefing
python -m app.main report
```

Generated report path:

- `reports/weekly_briefing_YYYYMMDD_HHMM.md`

> Tip: for a fully deterministic, offline run, set `PREFER_SAMPLE_DATA=true`
> in your `.env` (copy it from `.env.example` first). The agent then skips all
> live calls and uses sample data only.

### Option B — Live mode (observed macro + news + LLM)

```bash
# 1) (optional but recommended) isolate the environment
python -m venv .venv
.venv\Scripts\activate

# 2) Install deps
pip install -r requirements.txt

# 3) Enable live sources / LLM by adding your keys
copy .env.example .env   # then fill FRED_API_KEY / NEWSAPI_KEY / OPENAI_API_KEY

# 4) Validate config (no secrets are printed)
python -m app.main check-config

# 5) Run full workflow and generate report
python -m app.main report
```

### Option C — Web UI (interactive dashboard)

Prefer a visual, business-facing view? Launch the Streamlit dashboard. It calls
the same orchestrator/skills as the CLI, so scores, alerts, Q&A, and data
quality tags are identical — just rendered in a browser.

```bash
pip install -r requirements.txt
python -m streamlit run app/ui/streamlit_app.py --server.port 8501
```

Then open `http://localhost:8501` in your browser (it usually opens
automatically). Press `Ctrl + C` in the terminal to stop the server.

### About live-source warnings (expected behavior)

If a live source (e.g. FRED or NewsAPI) is temporarily unreachable, you may see
`WARNING` lines like `FRED fetch failed ... falling back to sample`. **This is
by design, not an error**: the pipeline degrades gracefully to tagged
`synthetic` sample data so a report is always produced. The run still finishes
with status `success`/`partial` and the briefing is written to `reports/`.

## CLI Commands

| Command | Purpose |
|---|---|
| `python -m app.main ingest` | Fetch + normalize data |
| `python -m app.main run_pipeline` | Run `ingest -> normalize -> analysis -> news_impact -> alert` |
| `python -m app.main analyze` | Show composite score snapshot |
| `python -m app.main alert` | Run and list alert outputs |
| `python -m app.main report` | Run full pipeline + write weekly briefing |
| `python -m app.main ask "..."` | Business Q&A with evidence |
| `python -m app.main check-config` | Key/connectivity check (no secrets printed) |
| `python -m app.main runs` | Run history |
| `python -m app.main alert-history` | Alert lifecycle history |

Example:

```bash
python -m app.main check-config
python -m app.main report
python -m app.main ask "What are the main risks in Canary Wharf?"
```

## Architecture

```text
app/
  main.py
  orchestrator/
  skills/
    ingest_skill.py
    normalize_skill.py
    analysis_skill.py
    news_impact_skill.py
    alert_skill.py
    qa_skill.py
    report_skill.py
    recommendation_skill.py
  data/
    models.py
    repository.py
  llm/
  ui/
  utils/
sample_data/
tests/
```

Persisted tables:

- `market_signals`
- `events_news`
- `alerts`
- `runs`

## Scoring and Alerts

Composite scores:

- Market Stress Score
- Rental Resilience Score
- Supply Risk Score (includes refurbishment pipeline)
- Submarket Opportunity Score

Alert rules currently implemented:

- `vacancy_deterioration`
- `demand_weakening`
- `supply_squeeze`
- `availability_overhang`
- `macro_shock`
- `data_staleness`

Severity guardrail:

- High severity requires observed evidence
- Synthetic-only triggers are auto-downgraded and tagged `[SYNTHETIC-TEST]`

## Data Sources

| Track | Domain | Source | Quality |
|---|---|---|---|
| Live API | Macro (policy rate, CPI, core CPI, unemployment, gilt, employment proxy) | FRED | `observed` |
| Live API | News/events | RSS + NewsAPI | `observed` |
| Sample | CRE core metrics | `sample_data/*.csv` | `synthetic` |
| Fallback | Macro/news when live fetch fails | `sample_data/*.csv` | `synthetic` |

Notes:

- CRE core is intentionally synthetic in this PoC (clear disclosure in outputs)
- `Office Employment` uses UK employment rate (`LREM64TTGBQ156S`) as a transparent proxy

## Tests

```bash
python -m pytest -q
```

Current status: `21 passed`.

## Limitations and Next Steps

- Replace synthetic CRE core with observed broker/public-report pipelines
- Add automated PDF extraction with page-level provenance for CRE reports
- Add scheduled execution and email/Slack delivery
- Expand Q&A into stronger retrieval over longer signal history
