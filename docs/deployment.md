# Deployment runbook (Render)

Deploys the API (FastAPI), the dashboard (Next.js), and managed Postgres from
[`render.yaml`](../render.yaml). One blueprint, one git push.

## Prerequisites

- A GitHub repository for this code (Render Blueprints deploy from GitHub).
- A free Render account.

## Steps

1. **Push to GitHub.** From the repo root:
   ```bash
   gh repo create cashflow-risk --private --source . --push   # or your own remote
   ```
2. **Create the Blueprint.** In Render: **New → Blueprint**, select the repo.
   Render reads `render.yaml` and provisions:
   - `cashflow-db` — managed Postgres (`DATABASE_URL` injected into the API).
   - `cashflow-api` — the Docker API; `CASHFLOW_JWT_SECRET` is generated; CORS
     trusts `*.onrender.com` via `CASHFLOW_ALLOWED_ORIGIN_REGEX`. Migrations run
     on start (`alembic upgrade head`).
   - `cashflow-web` — the Next.js dashboard.
3. **Wire the web → API URL (one manual step).** After the first deploy, copy the
   API URL (e.g. `https://cashflow-api.onrender.com`) into the **`cashflow-web`**
   service's `NEXT_PUBLIC_API_BASE` env var, then redeploy the web service with
   **Clear build cache** (it's inlined at build time).
4. **Verify.** `GET https://cashflow-api.onrender.com/api/health` → `{"status":"ok"}`.
   Open the web URL — it loads the public demo.

## Environment variables

| Variable | Service | Set by | Notes |
|---|---|---|---|
| `DATABASE_URL` | api | Render (from DB) | `postgres://…`; normalised to psycopg automatically |
| `CASHFLOW_JWT_SECRET` | api | Render (generated) | required in prod; the app refuses to start on the default |
| `CASHFLOW_ENV` | api | `production` | disables dev token minting |
| `CASHFLOW_ALLOWED_ORIGIN_REGEX` | api | blueprint | CORS allowlist for the dashboard domain |
| `NEXT_PUBLIC_API_BASE` | web | you (step 3) | the API's public URL |

## Important notes

- **Auth in production.** Dev token minting is off, so only the **public demo**
  works on the deployed site. Real uploads need a sign-in — that means adding a
  hosted IdP (the JWT seam already verifies its tokens). Until then, the deploy is
  for demoing the product (ideal for Phase 0 interviews).
- **DPIA.** Required before processing the first *real* sole-trader data. The
  public demo (synthetic) does not trigger it. See `security_privacy.md`.
- **Free tier.** Free web services cold-start after inactivity (first request is
  slow). Render's free Postgres expires after ~90 days — upgrade or recreate.
- **Migrations** run automatically on each API start; they are idempotent. To run
  manually: `uv run alembic upgrade head` with `DATABASE_URL` set.
- **Rollback.** Use Render's "Rollback" to a previous deploy; the DB is unchanged
  unless a migration ran — write migrations to be backward-compatible.
