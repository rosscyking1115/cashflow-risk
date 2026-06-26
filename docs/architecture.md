# Architecture (MVP)

Decided after review. The guiding principle: **one system of record, no
premature infrastructure.**

## System of record

- **PostgreSQL is the sole source of truth.** All canonical entities live here.
- **DuckDB is an ephemeral, in-process analytics engine** — spun up per forecast
  run (load from Postgres / parquet → compute → discard). It is **not a store**.
- **No browser-side data store (IndexedDB/Dexie).** The v1 "local-first" idea is
  incompatible with a server-side Python engine (sklearn/DuckDB/pandas cannot see
  data that never leaves the browser). Reframed as **"local-control"**: aggressive
  retention limits + one-click delete. A true in-browser (WASM) engine is a
  possible *future*, not the MVP.

## Deferred (do not build at MVP)

- **Redis + RQ/Arq.** A 13-week forecast over one SME's CSV computes in well under
  a second. Run synchronously, or use FastAPI `BackgroundTasks` for exports. Add a
  job broker only when connectors bring multi-minute syncs or batch scoring.
- **OpenTelemetry.** Sentry alone covers errors + basic perf for a two-service app,
  and avoids OTel's PII-leak surface. Revisit when there are multiple services.
- **Polars.** pandas is the interchange layer sklearn/LightGBM expect; heavy work
  goes to DuckDB SQL. A third dataframe dialect solves no problem we have.
- **Object storage for raw uploads.** Parse CSV in-process, persist only derived
  entities, discard the raw file. Add durable raw retention only if a feature
  truly needs it.

## Layers

```
CSV/XLSX upload ─┐
synthetic demo ──┤→ ingestion (validate) → Postgres (record)
                 │                              │
                 │              DuckDB (ephemeral query/aggregation)
                 │                              │
                 │            features (as-of) → forecasting / risk
                 │                              │
                 └──────────────────── reporting (action brief, CSV)
                                                │
                                FastAPI  →  Next.js dashboard
```

## Phase ordering

- **Phase 1:** generator → Postgres schema (single SoR) → validation → DuckDB
  engine over the data → baselines → action-brief templates → tests. No Redis,
  OTel, object storage, or IndexedDB.
- **Phase 2:** Next.js + shadcn + Recharts; synchronous upload → compute → render;
  **auth + tenant isolation + row-level checks land here** (hosted provider, not
  hand-rolled), not in a later hardening phase.
- **Phase 3+:** ML models, connectors (via a regulated open-banking provider).

## Frontend (Phase 2)

Next.js · TypeScript · Tailwind · shadcn/ui · Recharts. Design intent: a **calm
financial control room** — fast to scan, serious enough for an accountant, never
intimidating. Every score has a "why"; every warning has an action; uncertainty
is always shown. (`frontend-design`, `web-design-guidelines`,
`vercel-react-best-practices`.)
