# Cashflow Risk Intelligence — Agent Instructions

> **This is NOT an Expo / React Native project.** Ignore any Expo or mobile
> instructions that leak in from sibling repositories. This is a **Python**
> analytics engine with a **Next.js + FastAPI** web product layered on later.

## What this project is

A UK-focused **cashflow risk intelligence** tool for small businesses and their
accountants. The sharp wedge:

> Which late payments break my cash runway, and what should I do this week?

Primary goal is a **micro-SaaS that real UK SMEs would trust and use** — not a
portfolio artifact. That means: correctness, explainability, privacy, and
regulatory caution are first-class, not afterthoughts.

## Golden rules

1. **Never present a model score as certain truth.** Every risk score ships with
   a calibrated probability and a plain-English "why". Every warning ships with
   an action.
2. **This is decision support, not regulated advice.** Never emit wording that
   reads as tax, accounting, legal, credit, or investment advice. See
   `docs/security_privacy.md`.
3. **Data minimisation.** No raw financial data in logs or error reports. Real
   personal/financial data triggers a DPIA before processing — synthetic data
   does not. The MVP processes server-side; raw uploads are discarded after parse.
4. **Synthetic metrics are pipeline unit-tests, not evidence of predictive
   skill.** The data generator's latent mechanism must NOT be visible to the
   model. Predictive claims are only valid on held-out real data and against
   real UK benchmarks (GOV.UK Payment Practices Reporting).
5. **Baselines before ML.** Beat a deterministic-ledger forecast and a
   seasonal-naive baseline, with leakage-safe rolling-origin evaluation, before
   reaching for LightGBM.

## Toolchain

- Python ≥ 3.12, managed with **uv** (`uv sync`, `uv run pytest`, `uv run ruff`).
- pandas (not Polars) for interchange; **DuckDB** for heavy SQL — it is an
  *ephemeral in-process engine*, not a store.
- Tests with pytest. New engine logic is written **test-first** (see `docs/PLAN.md`).
- Lint/format with ruff; type-check with mypy (strict).

## Layout

- `src/cashflow_risk/domain/` — canonical entities (the ubiquitous language).
- `src/cashflow_risk/datagen/` — synthetic UK SME data generator.
- `src/cashflow_risk/ingestion/` — CSV/XLSX import + schema validation.
- `src/cashflow_risk/features/` — as-of feature store (leakage-safe).
- `src/cashflow_risk/forecasting/` — 13-week cash forecast (baselines first).
- `src/cashflow_risk/risk/` — late-payment risk scoring.
- `src/cashflow_risk/reporting/` — action briefs + exports.
- `CONTEXT.md` — the domain glossary (ubiquitous language).
- `docs/` — `PLAN.md`, `architecture.md`, `security_privacy.md`, `adr/`.

Read `docs/PLAN.md` before starting any phase of work.
