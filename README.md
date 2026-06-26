# Cashflow Risk Intelligence

> Working title. A UK-focused tool that tells a small business **which late
> payments could break its cash runway, when the risk appears, and what to do
> this week.**

Late payments cost UK SMEs an estimated £11bn a year. Most owners find out about
a cash shortfall when it is already happening. This tool forecasts a 13-week cash
runway, ranks the invoices and customers driving the risk, and produces a plain
-English action brief — *decision support, not regulated advice*.

## Status

Early build. **Phase 1: analytics engine on synthetic UK SME data.** Not yet a
deployable product. See [docs/PLAN.md](docs/PLAN.md) for the full roadmap and
[CONTEXT.md](CONTEXT.md) for the domain language.

## The wedge

Not "forecasting exists" — that is a crowded market (Float, Futrli, Fathom). The
wedge is **explainable, action-first late-payment risk**: every score has a why,
every warning has an action, and it works from a CSV upload in minutes.

## Quick start (engine)

```bash
uv sync                 # create venv + install deps
uv run pytest           # run the test suite
uv run ruff check .     # lint
```

## Principles

- **Trust first.** Calibrated probabilities, honest uncertainty, no false
  precision. Decision support — never tax, credit, or investment advice.
- **Privacy by retention.** Server-side processing; raw uploads discarded after
  parse; one-click delete. See [docs/security_privacy.md](docs/security_privacy.md).
- **Credible data science.** Leakage-safe rolling-origin evaluation; beat
  deterministic + seasonal-naive baselines before any ML; validate against real
  UK payment-practice benchmarks, never synthetic data alone.

## Architecture (MVP)

Python analytics engine → FastAPI → Next.js dashboard. PostgreSQL is the single
source of record; DuckDB is an ephemeral in-process query engine. No browser-side
data store, no background-job broker, no distributed tracing at MVP. See
[docs/architecture.md](docs/architecture.md).
