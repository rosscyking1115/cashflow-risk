# Postgres is the sole system of record; DuckDB is an ephemeral engine

The original plan proposed three coexisting stores — DuckDB, PostgreSQL, and
browser IndexedDB — with no declared system of record, which is three sources of
truth waiting to drift (dangerous for a financial tool). We decided **PostgreSQL
is the single source of truth**, **DuckDB is an ephemeral in-process analytics
engine** spun up per Forecast run (load → compute → discard, never a store), and
there is **no browser-side data store** at MVP.

## Considered Options

- *Local-first with IndexedDB* (v1 proposal): rejected — incompatible with a
  server-side Python engine (sklearn/DuckDB/pandas cannot see data that never
  leaves the browser). Reframed as "local-control": aggressive retention + delete.
- *DuckDB as a persistent store*: rejected — it is an analytics engine, not an
  OLTP system of record for multi-tenant financial data.

## Consequences

"Local-first" privacy claims are downgraded to "local-control". A true in-browser
(WASM) engine remains a possible future, but is a different, larger project.
