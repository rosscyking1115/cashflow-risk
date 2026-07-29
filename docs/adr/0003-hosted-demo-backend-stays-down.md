# The hosted demo backend stays down rather than change what the system is

The API behind the [live demo](https://cashflow-web-sidu.onrender.com/) stopped
responding. The web front end is healthy; the API returns nothing at all — TCP
connects at the edge in 0.06s and no HTTP response arrives, measured at 75s, 75s,
100s, 120s and 120s across several hours.

We decided to **leave the hosted backend down**, keep both public links, spend
nothing, and reject the change that would have made the demo work.

## Diagnosis, as far as it goes from outside

Render's own documentation supplies the mechanism. Free Postgres databases
"expire 30 days after creation" (14-day grace, then deletion), and this project's
[`render.yaml`](../../render.yaml) puts `cashflow-db` on `plan: free`. The API
starts with `alembic upgrade head && uvicorn …`, so a dead `DATABASE_URL` fails
migrations, the `&&` short-circuits, uvicorn never runs, nothing binds the port,
and the edge accepts TLS then waits for an origin that never answers. That is
exactly the observed signature.

Two of the three candidate states are ruled out on evidence:

| Candidate | Verdict |
| --- | --- |
| Free-tier cold start exceeding the client timeout | **Ruled out.** Render documents reactivation at "about one minute" behind a loading page. The web service woke in 23–33s. The API was given 100s+ repeatedly with no response, no loading page, and no reply even on a nonexistent path — a 404 would have proved an origin was up. |
| Suspended after exhausting free instance hours | **Ruled out.** Render suspends *all* free web services in a workspace when the 750 monthly hours run out. The API and the web service are both free and in the same workspace, and the web service serves 200 in under a second. |
| Failed deploy / crash loop | **Remaining, and consistent with every observation.** Mechanism above. |

**Not confirmed.** Closing this needs the Render dashboard, which the diagnosis
could not reach — no API key, no CLI, and signing in was not on the table. Two
checks would settle it:

1. `cashflow-db` — status and creation date. Does it read Expired or Deleted?
2. `cashflow-api` → Events and Logs — is the most recent deploy Failed, and does
   the boot log show a database connection error from `alembic upgrade head`,
   repeating?

## Considered Options

- **Pay for the cheapest Postgres that does not expire** — `Basic-256mb`,
  **$6/month** at the time of writing; the free tier is listed on Render's pricing
  page as "$0 (30-day limit)". Rejected: no spend is authorised on this project.
  This is the option that would actually fix it, and it is a standing offer rather
  than a closed door.

- ***** **Drop the `fromDatabase` binding so the API falls back to SQLite** —
  rejected, and this is the one worth explaining, because it looks like a free win
  and is not.

  The API defaults to `sqlite:///./cashflow.db` when `DATABASE_URL` is unset. The
  public demo endpoint generates synthetic data and needs no persistence, so
  unbinding the database would make the demo work immediately, at no cost.

  It was rejected because **it makes the system pass by changing what the system
  is.** [ADR 0001](0001-postgres-sole-record-duckdb-ephemeral.md) records that
  PostgreSQL is the single source of truth, chosen precisely because multiple
  stores in a financial tool are sources of drift. Free web services also lose all
  local file changes on redeploy and spin-down, so the "database" would be
  discarded continuously — runs, history and the append-only audit log would
  silently stop persisting while the documentation continued to describe them as
  persisted. The DPIA's retention and erasure measures rest on that store.

  A green demo bought by quietly contradicting the architecture is the same defect
  class this repository spent an audit removing: making a check pass by changing
  what it measures. See
  [release-check-2026-07-27.md](../release-check-2026-07-27.md).

  **Do not re-propose this as an obvious win.** It is only reopenable as a
  deliberate architectural change — a documented decision that the demo
  deployment is stateless and that persistence, history, audit and retention are
  local-only concerns — with the README, `architecture.md`, ADR 0001, the DPIA and
  the privacy notice all updated to match *before* the binding is dropped.

- **Stop advertising the demo** — remove the README link and clear the repository
  Website field. Rejected: unnecessary, given the front end now reports its own
  state accurately.

- **Add a "currently down" note to the README** — rejected. It would be true only
  until the service came back, and a status line that rots is the exact defect the
  audit catalogued as embedding a number where it goes stale. The application
  reports live state; the README stays condition-independent.

## Consequences

- **Both public links stay.** The README link and the repository Website field
  continue to point at the dashboard. The front end degrades visibly and says so:
  it distinguishes waking from unavailable, waits past the cold-start window
  before calling anything a failure, and tells the reader the code and its
  evaluation are in the repository regardless.
- **The demo is not reliably available**, and the README says so in
  condition-independent terms — free tier, sleeps when idle, sometimes
  unavailable.
- **Nothing about the project's substance depends on the host.** Every figure the
  demo would show is reproducible from a clean checkout with the commands in the
  README and [MODEL_CARD.md](../MODEL_CARD.md).
- Restoring the demo costs $6/month, or a deliberate and fully-documented move to
  a stateless deployment. Neither is authorised now.

## Status (29 Jul 2026)

Open. The backend is down, the diagnosis is as complete as it can be from outside,
and the two dashboard checks above are the next step whenever someone with access
wants to close it.

Separately and still unverified: `web/.nvmrc` was added so Render builds against
the same Node major as CI. Whether Render actually picked it up **has not been
confirmed** — that also needs the dashboard.

---

## Amendment — 29 Jul 2026: the demo is retired, and this record was incomplete

Everything above stands as written, including the SQLite rejection and its
do-not-re-propose clause. That reasoning was correct and remains so. This
amendment is appended rather than folded in, because what the original got wrong
is worth seeing.

### The original weighed two options and missed a third

It considered paying Render $6/month and rejecting the SQLite fallback, and
concluded there was nothing else. There was. **Neon offers a free Postgres with
no expiry** — 0.5 GB per project, 100 CU-hours per project per month (roughly 400
hours of a 0.25 CU compute), scale-to-zero after five minutes, and suspended
computes do not consume the allowance. Verified against Neon's own plan
documentation on 29 Jul 2026. Exceeding storage blocks writes and exhausting
compute suspends it; **neither deletes data**.

That defeats this ADR's own argument against the SQLite fallback. The objection
was that the fallback makes the system pass by changing what the system is —
sole-source-of-truth, persistence of runs and history and the audit log, the DPIA
measures resting on that store. **An external Postgres keeps every one of those
true. It is a different provider, not a different architecture.**

The **$6/month** figure was accurate for Render and wrong for the question. The
question was "what does a non-expiring Postgres cost", and the answer was zero;
the original answered "what does Render charge", which is a narrower question it
did not notice it had substituted.

An ADR that lists only the options its author thought of has the same defect as a
check that only tests what its author expected. This one did, and the record now
says so.

### The third option was declined, not defeated

**Neon would have worked.** It was not tried and found wanting; it was found,
verified, and then declined on portfolio grounds rather than technical ones.

The reason is that this repository does not need a hosted demo:

- The portfolio already carries four or five live demos, so this one demonstrates
  no capability that is not already shown elsewhere.
- What is distinctive here is an **honest negative result** — the evaluation found
  no edge over the baseline and says so. That lives in the README, in
  [model-evaluation.md](../model-evaluation.md), in [MODEL_CARD.md](../MODEL_CARD.md)
  and in these ADRs. **A dashboard renders none of it.**
- A hosted UI would prove a Next.js front end over a FastAPI backend, which is
  readable from the source in less time than the demo takes to wake.

Set against that: a migration adds a third-party free tier with its own limits and
its own ability to change them — the exact failure shape that produced this
situation — plus a persistence verification that never happened. `POST
/api/analyze/demo` does not touch the database, so a working demo would have
proved the API boots and nothing about whether runs, history and the audit log
survive a restart.

Worth stating plainly for the next reader: **Neon's docs are silent on whether
dormant free projects are archived or removed.** No policy is documented. Absence
of a documented clock is not a guarantee there is none, and this project has just
spent a fortnight on the consequences of a clock nobody noticed.

### What was kept

The [SQLite guard](../../src/cashflow_risk/db/session.py) was extracted from the
abandoned migration and merged on its own. Production now refuses to start unless
`DATABASE_URL` is set to a non-SQLite URL, so the architecture refused above
cannot arrive by way of a missing environment variable. That holds wherever the
database lives and whether or not anything is deployed. Four tests cover it, and
disabling the guard fails two of them.

### Consequences of retiring

- **The README no longer advertises a hosted demo.** The two-command local path is
  the way to run this: `uv sync` then `uv run python scripts/demo.py`.
- **The repository Website field is cleared.** A link with no context, pointing at
  a service that no longer answers, is worse than no link.
- **`cashflow-web` and `cashflow-api` are suspended, not deleted.** Suspension is
  reversible; deletion is not.
- **The expired Render database is abandoned, not rescued.** Its deletion clock is
  irrelevant — nobody should pay to save a database that is being replaced by
  nothing. Let it go.
- **`render.yaml` and the deployment runbook are kept**, marked as not currently
  deployed, with the free-Postgres expiry called out so the next person does not
  walk into it.

### This is reversible

Restoring a hosted demo later is a decision, not a rediscovery. The guard is
merged, the blueprint still describes the deployment, the free-tier trap is
documented in `render.yaml` itself, and Neon's free plan is recorded above with
the figures and the date they were verified. Anyone picking this up starts from
what was learned rather than from the beginning.

**Status: closed.** The hosted demo is retired. Reopening means deciding that a
running dashboard is worth more than it costs — not discovering that it is
possible.
