# Data Integrity & Authenticity Policy (binding)

This policy governs every record the agent ingests, stores, and reports. It is
enforced in code (`normalize_skill` validation + `data_quality` tagging) and in
output (`report_skill` / `qa_skill` / `alert_skill`).

## Core principles
1. If a value can be fetched from a real API / public source, do NOT use a mock.
2. Every non-real / inferred value MUST be tagged `data_quality = synthetic` or
   `estimated`.
3. All outputs (report / Q&A / alerts) MUST distinguish **Observed** vs
   **Estimated** vs **Synthetic**.
4. Synthetic data must never be presented as a real market fact.

## Classification in this PoC

| Domain | Field group | Required quality | Source in this build |
|---|---|---|---|
| Macro (Hard Real) | policy_rate, cpi, core_cpi, unemployment_rate, gilt_yield, office_employment | `observed` | FRED API (series_id + source_url + retrieved_at). Falls back to `synthetic` sample only if the API is unreachable. `office_employment` uses the UK employment rate 15-64 (`LREM64TTGBQ156S`) as a transparently-labelled labour-demand proxy (no FRED series exists for UK *office* headcount). |
| News/Events (Hard Real) | headline, published_at, source_name, source_url, snippet | `observed` | Live RSS. Falls back to `synthetic` sample only if all feeds fail. |
| Time/metadata (Hard Real) | retrieved_at, run_id, logs | system-generated | Runtime only, never hand-authored. |
| CRE core (Best-effort Real) | prime/grade A rent, vacancy, availability, take-up, pipeline, pre-let | currently `synthetic` | `sample_data/*.csv` — no stable free public series available within the deadline. Tagged `synthetic_reason=missing_public_source`. |

## Field contract
Every `market_signals` / `events_news` row carries:
- `data_quality`: `observed` | `estimated` | `synthetic`
- `source`: provenance label (e.g. `FRED`, `sample_data/office_rent_by_submarket.csv`)
- `source_url`: nullable, present for `observed` web/API rows
- `source_detail`: series_id / report page / mock-style label
- `retrieved_at`: ISO timestamp generated at ingest time
- `synthetic_reason`: nullable (`missing_public_source` | `alert_test_fixture`)

## Enforcement rules
- A row missing `source`/`source_url`/`retrieved_at` may NOT be classified `observed`.
- Synthetic rows do not drive "final market conclusions" unless explicitly allowed,
  and then only with a disclosure.
- `High` severity alerts must be backed by `observed` data. A synthetic-triggered
  alert is auto-downgraded one level and tagged `[SYNTHETIC-TEST]`.
- Q&A prefers `observed` evidence; any use of `estimated`/`synthetic` is stated in
  the answer and lowers confidence.
- Reports include a `Data Provenance & Quality` section and, when synthetic rows
  exist, a `Synthetic Data Disclosure` section plus a "real-source backlog".

## Real-source onboarding backlog (TODO)
- [ ] Prime / Grade A rent: ingest from public broker market reports (JLL/Savills/CBRE
      quarterly PDFs) with page-level provenance, or a licensed CRE data feed.
- [ ] Vacancy / availability: same as above.
- [ ] Take-up / pipeline / pre-let / refurbishment: Deloitte London Office Crane Survey
      (public PDF) extraction with page citations.
- [x] Gilt yields: FRED `IRLTLT01GBM156N` (UK 10y) — live observed.
- [x] Core CPI: FRED `GBRCPICORMINMEI` (UK all items ex food & energy) — live observed.
- [x] Employment: FRED `LREM64TTGBQ156S` (UK employment rate 15-64) — live observed,
      used as a labour-demand proxy for office occupiers. Upgrade path: ONS regional
      London office-using employment when a stable public API is available.
