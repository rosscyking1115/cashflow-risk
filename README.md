# Cashflow Risk Intelligence

[![CI](https://github.com/rosscyking1115/cashflow-risk/actions/workflows/ci.yml/badge.svg)](https://github.com/rosscyking1115/cashflow-risk/actions/workflows/ci.yml)

A tool for UK small businesses that answers three questions about late payments:
**which** ones could break your cash runway, **when** the risk appears, and **what
to do this week** about it.

Late payments cost UK SMEs an estimated £11bn a year, and most owners only find
out about a shortfall once it is already happening. Cashflow Risk Intelligence
takes a CSV of your invoices, forecasts a 13-week cash runway, ranks the invoices
and customers driving the risk, and writes a plain-English action brief — every
score with a reason, every warning with a next step.

> [!IMPORTANT]
> This is decision support, not regulated advice. It never gives tax, credit, or
> investment advice, and it profiles companies (via Companies House) — never
> sole-trader individuals.

## Features

- **13-week cash forecast** from your invoice ledger, timed by a risk-adjusted view
  of when each invoice will actually be paid.
- **Invoice & customer risk ranking** by expected cash at risk (amount × probability
  of late payment), each with plain-English drivers.
- **Action brief** — a deterministic, readable summary of the week's chase list and
  the runway impact.
- **Companies House enrichment** — a customer's overdue filings, insolvency, and
  charges feed the late-payment score; a daily job keeps the signals fresh.
- **Multi-tenant with real RBAC** — owners and invited accountants, every query
  scoped to a tenant, cross-tenant access refused.
- **Trust built in** — PII-scrubbed error reporting, no financial data in logs,
  CSV-injection-safe exports, upload hardening, an audit log, self-serve
  export/delete, and a 24-month retention purge.

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

Run the full dashboard (two processes):

```bash
# 1. API. CASHFLOW_ENV=dev enables a local token so uploads work without a
#    hosted login; omit it and only the public demo is available.
CASHFLOW_ENV=dev uv run uvicorn cashflow_risk.api:app --port 8000

# 2. Web dashboard (another terminal); npm install only the first time.
cd web && npm install && npm run dev   # http://localhost:3000
```

The dashboard opens on the public demo. Use **Invoices CSV** to analyse your own
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
from [`render.yaml`](render.yaml) — push to GitHub, then **New → Blueprint**. Full
steps in [docs/deployment.md](docs/deployment.md).

## Project layout

| Path | What |
|---|---|
| `src/cashflow_risk/` | The engine: `domain`, `datagen`, `features`, `forecasting`, `risk`, `reporting`, `ingestion`, `enrichment`, `db`, `auth`, `api` |
| `web/` | Next.js dashboard |
| `scripts/` | `demo.py`, the risk bake-off, and the daily maintenance job |
| `alembic/` | Database migrations |
| `docs/` | Plan, architecture, and the security/privacy docs below |

## Documentation

- [docs/PLAN.md](docs/PLAN.md) — roadmap, phasing, and decision gates
- [CONTEXT.md](CONTEXT.md) — the domain model and ubiquitous language
- [docs/architecture.md](docs/architecture.md) — architecture and its trade-offs
- [SECURITY.md](SECURITY.md) — security posture and vulnerability reporting
- [docs/threat-model.md](docs/threat-model.md) — STRIDE threat model
- [docs/security_privacy.md](docs/security_privacy.md) · [docs/dpia.md](docs/dpia.md) · [docs/privacy-notice.md](docs/privacy-notice.md)
