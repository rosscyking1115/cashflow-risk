# Architecture

The guiding principle: **one system of record, no premature infrastructure.**

This page describes what is built. Where a decision was taken but not implemented,
it says so — an architecture doc that describes intentions in the present tense is
how a repository starts lying about itself.

## System of record

- **PostgreSQL is the sole source of truth.** All canonical entities live here.
  Locally it falls back to a SQLite file, which is the same schema through
  SQLAlchemy.
- **No browser-side data store (IndexedDB/Dexie).** The v1 "local-first" idea is
  incompatible with a server-side Python engine (sklearn and pandas cannot see
  data that never leaves the browser). Reframed as **"local-control"**: aggressive
  retention limits + one-click delete. A true in-browser (WASM) engine is a
  possible *future*, not something that exists.
- **DuckDB is not used.** [ADR 0001](adr/0001-postgres-sole-record-duckdb-ephemeral.md)
  decided it would serve as an ephemeral in-process analytics engine, never a
  store. That part was never built: the forecast and feature paths are plain
  pandas and Python over data loaded from the record, which is fast enough for one
  SME's ledger. The dependency has been dropped rather than left in the runtime
  image unused. The ADR's actual decision — Postgres is the only store — stands.

## Deferred (deliberately not built)

- **Redis + RQ/Arq.** A 13-week forecast over one SME's CSV computes in well under
  a second. Run synchronously, or use FastAPI `BackgroundTasks` for exports. Add a
  job broker only when connectors bring multi-minute syncs or batch scoring.
- **OpenTelemetry.** Sentry alone covers errors + basic perf for a two-service app,
  and avoids OTel's PII-leak surface. Revisit when there are multiple services.
- **Polars.** pandas is the interchange layer sklearn and LightGBM expect. A second
  dataframe dialect solves no problem we have.
- **Object storage for raw uploads.** Parse CSV in-process, persist only derived
  entities, discard the raw file. Add durable raw retention only if a feature
  truly needs it.

## Layers

```
CSV/XLSX upload ─┐
synthetic demo ──┤→ ingestion (validate) → Postgres (record)
                 │                              │
                 │            features (as-of) → forecasting / risk
                 │                              │
                 └──────────────────── reporting (action brief, CSV)
                                                │
                                FastAPI  →  Next.js dashboard
```

## Frontend

Next.js, TypeScript, Tailwind, and hand-written React components — no component
library and no charting library. The runway readout and cash instrument are plain
SVG and CSS, which is why [`web/package.json`](../web/package.json) has four
runtime dependencies.

Design intent: a **calm financial control room** — fast to scan, serious enough for
an accountant, never intimidating. Every score has a "why", every warning has an
action, and uncertainty is always shown.

## Not yet built

- ML models beyond the bake-off rungs, which run at training time only and never
  ship in the runtime image.
- Bank and accounting connectors, which would need a regulated open-banking
  provider.
