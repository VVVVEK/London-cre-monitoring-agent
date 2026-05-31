---
title: London Office CRE Monitoring Agent
subtitle: Business-ready PoC for Nan Fung
---

# Slide 1 — Business Problem and Goal

**Current pain point**

- Market monitoring is manual, fragmented, and slow.
- Analysts spend time collecting data instead of interpreting it.
- Reports become outdated quickly and are hard to trace to source evidence.

**Goal**

Build an AI agent that continuously monitors the London office market and gives
the business team a trusted weekly view of:

- where risk is rising,
- where opportunities are improving,
- and why (with traceable evidence).

---

# Slide 2 — What We Built

**Skill-based architecture**

```text
ingest -> normalize -> analysis -> news_impact -> alert -> qa -> report
```

- Modular Python skills orchestrated into pipeline, weekly briefing, and Q&A flows.
- Persisted data model (`market_signals`, `events_news`, `alerts`, `runs`) for auditability.
- Explainable scoring and rule-based alerts (not a black box).
- LLM-enhanced but not LLM-dependent (works without model keys).

---

# Slide 3 — Coverage vs Business Requirements

**Market dimensions covered**

- Rents: Prime + Grade A
- Occupancy: Vacancy + Availability
- Demand: Take-up + Net Absorption
- Supply: Pipeline, Completions, Refurbishment, Pre-let
- Submarkets: City, West End, Canary Wharf, Midtown
- Macro: rates, CPI/core CPI, unemployment, gilt yield, employment proxy
- Demand drivers: hybrid work, ESG, flight-to-quality, tenant moves, financing
- News/event monitoring with directional impact

**Scoring & alerts**

- Composite scores: Stress, Resilience, Supply Risk, Opportunity
- Alert rules: vacancy deterioration, demand weakening, supply squeeze,
  availability overhang, macro shock, data staleness

---

# Slide 4 — Example Outputs

**Weekly briefing (auto-generated)**

- Executive summary
- Submarket deep dive table
- Risk and opportunity narrative
- Alert list with lifecycle and suggested actions
- Source freshness, watchlist, and provenance disclosure

**Alert sample (Canary Wharf)**

- Supply squeeze
- Vacancy deterioration
- Demand weakening
- Availability overhang
- (Macro and staleness conditions when triggered)

**Q&A output**

- Direct answer
- Key points
- Evidence list (`source`, `date`, `metric`, `value`, `quality`)
- Confidence + explicit limitations

---

# Slide 5 — Data Trust and Governance

**Trust controls built into the PoC**

- Every row is tagged: `observed`, `estimated`, or `synthetic`
- Provenance fields enforced (`source`, `source_url`, `retrieved_at`)
- Synthetic-only alerts are downgraded and explicitly tagged `[SYNTHETIC-TEST]`
- Weekly report includes a dedicated synthetic disclosure section

**Why this matters**

- Business users can act faster **without** losing auditability
- Leadership can clearly distinguish live evidence vs demo assumptions

---

# Slide 6 — Limitations and Production Roadmap

**Current limitation**

- CRE core market metrics are synthetic sample data in this PoC.

**Roadmap to production**

1. Onboard observed CRE data sources (broker reports / licensed feed).
2. Add source-specific extraction with page-level citations.
3. Schedule automated runs and push outputs to email/Slack.
4. Deploy a lightweight web dashboard for self-serve monitoring.
5. Expand Q&A into richer retrieval over full historical data.

**Expected outcome**

A production-grade market intelligence agent that reduces manual monitoring
effort and improves speed and quality of CRE decision support.