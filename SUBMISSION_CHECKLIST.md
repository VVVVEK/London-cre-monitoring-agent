# Submission Checklist (Nan Fung Technical Assessment)

Use this checklist before sharing the GitHub repository and slides.

## A) Required Deliverables

- [ ] Testable, runnable AI agent PoC (Python)
- [ ] 3-6 slides for business audience
- [ ] Clear run instructions
- [ ] Data quality disclosure (`observed` vs `synthetic`)

## B) Repository Hygiene

- [ ] `.env` is **not** committed
- [ ] `*.db`, logs, caches are **not** committed
- [ ] No API keys or secrets in code, docs, commit history
- [ ] `README.md` is English, up to date, and reproducible
- [ ] `requirements.txt` installs cleanly

## C) Reproducibility (Run This Before Submission)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main check-config
python -m app.main report
python -m pytest -q
```

Expected:

- `check-config` prints connection/key status (no secrets exposed)
- `report` generates `reports/weekly_briefing_*.md`
- tests pass (currently `21 passed`)

## D) Feature Coverage Check

- [ ] Rent monitoring (Prime + Grade A)
- [ ] Vacancy + Availability
- [ ] Take-up + Net Absorption
- [ ] Supply pipeline (pipeline/completions/refurb/pre-let)
- [ ] Submarket analysis (City/West End/Canary Wharf/Midtown)
- [ ] Macro monitoring (rates/CPI/core CPI/unemployment/gilt/employment proxy)
- [ ] News-based demand drivers (hybrid, ESG, flight-to-quality, tenant moves, financing)
- [ ] Explainable scoring and alerting
- [ ] Weekly business briefing output

## E) Integrity / Trust Check

- [ ] Every signal/event row includes source metadata
- [ ] Synthetic data clearly labeled in outputs
- [ ] Synthetic-only alerts are downgraded and tagged `[SYNTHETIC-TEST]`
- [ ] Report includes provenance and synthetic disclosure sections

## F) Slides Checklist (3-6 pages)

- [ ] Slide 1: Business problem and objective
- [ ] Slide 2: Agent architecture and data flow
- [ ] Slide 3: Demo outputs (scores, alerts, report, Q&A)
- [ ] Slide 4: Business value and impact
- [ ] Slide 5: Limitations and next steps
- [ ] Optional slide 6: Rollout plan / implementation roadmap

## G) Final Submission Package

- [ ] GitHub repository URL
- [ ] Slide file (or markdown slide script)
- [ ] Short email note highlighting:
  - What the agent does
  - How to run it in 2-3 commands
  - What is observed vs synthetic
  - What you would build next in production
