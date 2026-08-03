# Running it locally

Everything needed to run the engine, the dashboard, the evaluation and the checks
on your own machine. The README covers the two-command path; this page is the rest.

You need [uv](https://docs.astral.sh/uv/) (Python 3.12) and Node.js 20+. No
accounts and no API keys — every default is safe and local.

## The engine

```bash
uv sync                          # create the venv + install deps
uv run python scripts/demo.py    # print an action brief for a synthetic SME
```

## Reproduce the evaluation

```bash
uv run python scripts/eval_risk_baseline.py      # rules-baseline metrics
uv run python scripts/bakeoff_risk.py            # rules vs logistic vs GBM, backtested
uv run python scripts/null_risk_bakeoff.py       # what a random scorer scores on the same folds
uv run python scripts/controls_risk_generator.py # is the benchmark circular? (no)
```

Read [evaluation-null.md](evaluation-null.md) before quoting any figure the
bake-off prints. The last two commands are why.

The gradient-boosting rung needs the training dependency group
(`uv sync --group train`); without it the bake-off prints a note and skips that
rung rather than failing.

## The dashboard

Two processes.

```bash
# 1. API. CASHFLOW_ENV=dev enables a local token so uploads work without a
#    hosted login; omit it and only the public demo is available.
CASHFLOW_ENV=dev uv run uvicorn cashflow_risk.api:app --port 8000
```

```bash
# 2. Web dashboard (another terminal); npm install only the first time.
cd web && npm install && npm run dev   # http://localhost:3000
```

It opens on the public demo. **Invoices CSV** analyses your own export; the tenant
comes from the token, never from client input.

## Configuration

Configuration comes from the environment. The defaults are safe, so it runs
locally with none of it set. Copy [`.env.example`](../.env.example) to `.env` to
change anything.

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

In production the engine **refuses to start** without a non-SQLite `DATABASE_URL`,
and refuses to start on the default JWT secret. Both are deliberate: a documented
guarantee that quietly degrades is worse than one that fails loudly.

## Database and migrations

Local dev creates the SQLite tables on startup. Managed databases use Alembic, and
the API runs `alembic upgrade head` when it deploys:

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

Every push and pull request runs those, plus a check that the migrations apply to
an empty database and still match the models (`alembic upgrade head` and
`alembic check`), plus the Next.js production build. See
[.github/workflows/ci.yml](../.github/workflows/ci.yml).

The type check is a gate, not a habit: `uv run mypy` runs as its own CI step with
no `continue-on-error`, so a type error fails the build and the branch does not
merge. It covers the `cashflow_risk` package; `tests/` and `scripts/` are outside
its scope.
