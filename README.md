# Cashflow Risk Intelligence

> Full-stack engineering · applied fintech data science · production-grade security.

[![CI](https://github.com/rosscyking1115/cashflow-risk/actions/workflows/ci.yml/badge.svg)](https://github.com/rosscyking1115/cashflow-risk/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Typed: mypy strict](https://img.shields.io/badge/mypy-strict-blue.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A worked, end-to-end project that models a real problem: which of a UK small
business's unpaid invoices could break its cash runway, **when** the risk appears,
and **what to do this week** about it. From an invoice CSV it forecasts a 13-week
cash runway, ranks invoices by expected cash at risk (late-payment probability ×
amount), enriches customer risk with Companies House filings, and writes a
plain-English action brief — every score with a reason.

It brings together three areas that rarely appear in one project:
a **Python analytics engine**, **applied data science** on late-payment risk done
honestly, and a **security/privacy posture** built for confidential financial data.

> [!NOTE]
> This is a reference project, not a commercial product. It is not for sale, holds
> no real customer data, and the phased product roadmap and production-pivot plan
> in [`docs/`](docs/) are **frozen** — kept as a record of the planning and
> threat-modelling, not as work in progress.

**[▶ Live demo](https://cashflow-web-sidu.onrender.com/)** — opens on a synthetic
dataset, no sign-in. (Free-tier host; the first load may take ~30s to wake.)

![The dashboard on synthetic data: a 13-week cash-runway readout and forecast, the invoices ranked by cash at risk with plain-English drivers, and the week's recommended action.](docs/images/dashboard.png)

<p align="center"><em>The dashboard on synthetic demo data — runway forecast, cash-at-risk ranking, and the weekly action. Every score carries its reason.</em></p>

## What it covers

| Area | Highlights |
|---|---|
| **Full-stack** | Pure-Python analytics engine behind a FastAPI service; PostgreSQL system-of-record with SQLAlchemy + Alembic migrations; Next.js/React/Tailwind dashboard; Clerk auth; deployed on Render; GitHub Actions CI (ruff, mypy-strict, pytest, migration-apply-and-drift check, Next build) with SHA-pinned actions |
| **Applied data science** | Leakage-safe as-of feature store; a pinned late-payment label with censoring; **rolling-origin, group-aware backtest**; the right metrics for a rare, ranked problem (PR-AUC vs prevalence, top-decile precision, calibration); a rules → logistic → gradient-boosted bake-off tracked in MLflow; an **anti-circular synthetic data generator** (latent mechanism the model never sees) |
| **Security & governance** | Multi-tenant isolation + RBAC with cross-tenant refusal (tested); STRIDE threat model + DPIA + privacy notice; PII-scrubbed error reporting **enforced by a test**; CSV-injection-safe exports; upload hardening; append-only audit log; retention auto-purge; self-serve data export/delete |
| **Engineering discipline** | Test-first throughout (150+ tests), strict typing, deep-module design, honest documentation of what does and doesn't work |

The data-science honesty is deliberate and, for this domain, the point: on the
synthetic data the fitted model **ties** the rules baseline — and the project
**explains why** (a latent "health-oracle" ceiling; the predictive signal is a
macro factor that is unobservable at prediction time without leakage). It measures
its models with a credible backtest rather than claiming a number it can't defend.
The full write-up, with the numbers, is in
[docs/model-evaluation.md](docs/model-evaluation.md).

## Features

- **13-week cash forecast** from an invoice ledger, timed by a risk-adjusted view
  of when each invoice will actually be paid.
- **Invoice & customer risk ranking** by expected cash at risk (amount × probability
  of late payment), each with plain-English drivers.
- **Action brief** — a deterministic, readable summary of the week's chase list and
  the runway impact.
- **Companies House enrichment** — a customer's overdue filings, insolvency, and
  charges feed the late-payment score; a daily job keeps the signals fresh.
- **Multi-tenant with real RBAC** — owners and invited accountants, every query
  scoped to a tenant, cross-tenant access refused (see Security & privacy below).

## Security & privacy

The project treats confidential financial data as a first-class constraint —
security and privacy are build-time requirements, several of them enforced by
tests:

- **Multi-tenant isolation & RBAC** — every query is scoped to a tenant; owners
  and invited accountants have distinct roles; cross-tenant access is refused
  (and that refusal is a test).
- **Data minimisation** — raw uploads are never stored, only derived results.
- **No sensitive data in logs or error reports** — Sentry runs with no PII, no
  local variables, no request bodies, and `before_send` redaction; a test asserts
  no financial fields reach the logs.
- **Safe by construction** — CSV-formula-injection-escaped exports, upload
  hardening (size/row limits, content sniffing), an append-only audit log,
  self-serve export/delete, and a 24-month retention purge.

The posture is documented, not just implemented: a
[STRIDE threat model](docs/threat-model.md), a
[DPIA](docs/dpia.md), a [privacy notice](docs/privacy-notice.md), and a
[security policy](SECURITY.md).

## How it works

```
 Next.js dashboard ──TLS + JWT──> FastAPI engine ──> PostgreSQL (system of record)
   (Clerk sign-in)                    │
                                      ├──> Companies House Public Data API (read)
                                      └──> Sentry (errors, PII-scrubbed)
```

The engine is a pure-Python analytics core (leakage-safe feature store, forecast
baselines, a rules-based risk scorer) exposed over FastAPI. PostgreSQL is the sole
system of record; only derived results are stored, never raw uploads. A separate,
training-time-only lane holds the risk-model bake-off (rules → logistic →
gradient-boosted) with MLflow tracking — it never ships in the runtime image.

## Getting started

**Prerequisites:** [uv](https://docs.astral.sh/uv/) (Python 3.12) and Node.js 20+.

Run the engine and see the action brief on synthetic data:

```bash
uv sync                          # create the venv + install deps
uv run pytest                    # run the test suite
uv run python scripts/demo.py    # print an action brief for a synthetic SME
```

See the model evaluation for yourself:

```bash
uv run python scripts/eval_risk_baseline.py   # rules-baseline metrics
uv run python scripts/bakeoff_risk.py         # rules vs logistic vs GBM, backtested
```

Run the full dashboard (two processes):

```bash
# 1. API. CASHFLOW_ENV=dev enables a local token so uploads work without a
#    hosted login; omit it and only the public demo is available.
CASHFLOW_ENV=dev uv run uvicorn cashflow_risk.api:app --port 8000

# 2. Web dashboard (another terminal); npm install only the first time.
cd web && npm install && npm run dev   # http://localhost:3000
```

The dashboard opens on the public demo. Use **Invoices CSV** to analyse a sample
export — the tenant is always taken from the token, never client input.

> [!NOTE]
> Synthetic data is for demonstration and pipeline tests only. Predictive claims
> are made against real UK payment-practice benchmarks, never synthetic data
> alone (see [docs/adr/0002](docs/adr)).

## Configuration

The service reads configuration from the environment; secure defaults mean it runs
locally with none of it set.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (defaults to a local SQLite file) |
| `CASHFLOW_JWT_SECRET` | Signing secret; **required** in production |
| `CASHFLOW_ENV` | `dev` enables the local dev-token endpoint |
| `CLERK_JWKS_URL`, `CLERK_ISSUER` | Enable Clerk-verified sign-in on the API |
| `COMPANIES_HOUSE_API_KEY` | Enables customer risk enrichment |
| `SENTRY_DSN` | Enables PII-scrubbed error reporting (optional) |
| `CASHFLOW_RETENTION_DAYS` | Auto-purge window for results (default 730) |
| `NEXT_PUBLIC_API_BASE` | Points the web app at a non-default API |

## Database and migrations

Local dev auto-creates SQLite tables on startup. Managed databases use Alembic,
and the API runs `alembic upgrade head` on deploy:

```bash
uv run alembic upgrade head                              # apply migrations
uv run alembic revision --autogenerate -m "describe it"  # after a model change
```

## Testing and CI

```bash
uv run pytest          # tests
uv run ruff check .    # lint
uv run mypy            # type-check (strict)
```

Every push and pull request runs all of the above plus a migrations-apply-and-match
check (`alembic upgrade head` + `alembic check`) and the Next.js production build
([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Deployment

The API, dashboard, managed Postgres, and a daily maintenance cron deploy to Render
from [`render.yaml`](render.yaml) as a blueprint — how the [live demo](https://cashflow-web-sidu.onrender.com/)
is hosted. Details in [docs/deployment.md](docs/deployment.md).

## Project layout

| Path | What |
|---|---|
| `src/cashflow_risk/` | The engine: `domain`, `datagen`, `features`, `forecasting`, `risk`, `reporting`, `ingestion`, `enrichment`, `db`, `auth`, `api` |
| `web/` | Next.js dashboard |
| `scripts/` | `demo.py`, the model evaluation + risk bake-off, and the daily maintenance job |
| `alembic/` | Database migrations |
| `docs/` | Architecture, the security/privacy docs below, and the (frozen) plan |

## Documentation

- [docs/model-evaluation.md](docs/model-evaluation.md) — how the risk model is measured, and the honest result
- [docs/architecture.md](docs/architecture.md) — architecture and its trade-offs
- [CONTEXT.md](CONTEXT.md) — the domain model and ubiquitous language
- [SECURITY.md](SECURITY.md) — security posture and vulnerability reporting
- [docs/threat-model.md](docs/threat-model.md) — STRIDE threat model
- [docs/security_privacy.md](docs/security_privacy.md) · [docs/dpia.md](docs/dpia.md) · [docs/privacy-notice.md](docs/privacy-notice.md)
- [docs/PLAN.md](docs/PLAN.md) · [docs/production-readiness.md](docs/production-readiness.md) — the **frozen** product roadmap and production-pivot decisions (retained to show the thinking; not in progress)
