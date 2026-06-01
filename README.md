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

```bash
# 1) Create environment
python -m venv .venv
.venv\Scripts\activate

# 2) Install deps
pip install -r requirements.txt

# 3) Optional: enable live sources / LLM
copy .env.example .env

# 4) Validate config
python -m app.main check-config

# 5) Run full workflow and generate report
python -m app.main report
```

Generated report path:

- `reports/weekly_briefing_YYYYMMDD_HHMM.md`

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

## Streamlit Demo (Optional)

```bash
python -m streamlit run app/ui/streamlit_app.py --server.port 8501
```

The UI calls the same orchestrator/skills as the CLI and preserves quality tags
and evidence disclosure.

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
