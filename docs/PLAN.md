# Cashflow Risk Intelligence — Build Plan (v2, optimised)

> This is the working plan. It supersedes the original
> `SME_Cashflow_Risk_Intelligence_Plan.md`, restructured after a three-angle
> review (product/GTM, data-science/ML, architecture/security/regulatory).
> **Primary goal: a micro-SaaS that UK SMEs and accountants would trust and
> use.** Validation leads; the build follows demand.
>
> **v3 update (§0.1):** re-evaluated by three agents (product strategy,
> architecture/skills-fit, Companies House API research) after a prompt to add a
> filing-risk feature and "naturally use missing skills". Headline: **stay
> micro-SaaS-first; Companies House is a counterparty *risk feature*, not a second
> dashboard; adopt only the skills the wedge actually demands.**

## 0. What changed from v1, and why

Three independent reviews converged on the same structural problems. The fixes
below are baked into the phasing.

| # | Problem in v1 | Fix in v2 |
|---|---|---|
| A | Refused to pick a primary goal; tested demand last (Phase 5) | **Micro-SaaS first.** Demand is validated in Phase 0 with interviews + a paper mock-up, as a hard gate before building. |
| B | Trained *and* evaluated the risk model on self-generated synthetic data → circular; "beats baselines" proves nothing | Generator built from a **latent mechanism the model is never given**; delay/late-rate distributions **anchored to real GOV.UK Payment Practices data**; synthetic metrics are **pipeline unit-tests**, predictive claims only on real data. |
| C | Three stores (DuckDB + Postgres + IndexedDB), no system of record; "local-first IndexedDB" contradicts a server-side Python engine | **Postgres = sole record. DuckDB = ephemeral in-process engine. Drop IndexedDB.** "Local-first" → "local-control" (retention + delete). Defer Redis/RQ, OpenTelemetry, object storage, Polars. |
| D | Auth/tenant-isolation in Phase 4 but a public multi-user demo in Phase 2; DPIA gated on connectors | **Auth + tenant isolation move to Phase 2.** DPIA triggered by **first real personal/financial data**, not connectors. Add ICO fee, CSV-injection defence, Sentry PII scrubbing, harder MTD/VAT wording. |
| E | ~10 "core" MVP features when the wedge needs ~3 | **MVP = 13-week forecast (P50) + invoice ranking by cash-at-risk + action brief + CSV/demo import.** Defer VAT estimation, anomaly/dedup, full scenario planner (keep one toggle), PDF, P10/P90 bands. |
| F | "Late payment" label undefined; eval split named but under-specified | **Label pinned now** (issue-time, censoring handled). As-of feature store, rolling-origin backtest, group-aware splits, **asymmetric/pinball forecast loss + shortfall-event recall**, PR-AUC vs prevalence, quantified gate thresholds. |

## 0.1 v3 re-evaluation — Companies House & the "missing skills"

Three agents converged on these verdicts:

- **Stay micro-SaaS-first (~85/15).** "Naturally use missing skills" is a
  portfolio motive; adopt a skill only when the wedge demands it, in the phase it
  demands it. The skills that *fit* are the ones this plan already arrived at
  independently — that's the filter.
- **Companies House = a counterparty risk *feature*, not a parallel compliance
  dashboard.** It enriches the late-payment score of the user's *customers* (who
  are often limited companies); the output stays cash-at-risk + chase-this-week. A
  standalone "your filing deadline is in 14 days" surface splits the product
  across two personas (owner vs accountant) — defer it to Phase 5+ as a separate
  module, only if Gate 5 passes.
- **CH scope is narrow and must be stated:** Companies House lists **limited
  companies + LLPs only — sole traders / freelancers are NOT on it.** So CH helps
  score *incorporated customers*; it does nothing for a sole-trader user's own
  filings (their equivalent is the fixed 31 Jan HMRC Self Assessment date — a
  static reminder, not an API lookup).
- **Highest-leverage architectural change: replace `business_id == user_id` with a
  `Membership(user_id, business_id, role)` model.** Real RBAC (not a toy), unblocks
  the accountant/advisor channel, gives CH a home (companies are shared across
  tenants), enables cross-client export — and is cheap because `repository.py`
  already scopes every query by `business_id`, so RBAC is a thin authorization
  layer in front of an existing seam.

**Skills filter (verdicts):**

| Skill | Verdict | Where |
|---|---|---|
| Auth / **RBAC** (owner / invited accountant) | **Do now** | `Membership` model; Clerk Organizations |
| **Excel** export | **Do now** | `GET /api/runs/{id}/export.xlsx` over the persisted payload, `=+-@`-escaped |
| **MLflow** | Phase 3 only | Tracking-only, training-time, **outside** the SaaS runtime |
| **Orchestration** (Prefect/Dagster) | When CH refresh exists | Start as a **Render Cron** job calling plain `refresh()`/`recompute()` fns; wrap in Prefect later at real multi-stage-DAG scale |
| **Snowflake** / **dbt** / **Power BI** | **Out of product scope** | Would distort a lean per-tenant SaaS. Pursue only as a deliberate *separate* data-platform/BI project, or confine to an internal benchmark lane (GOV.UK data + anonymised cohort stats — never tenant data). Power BI is reachable for free as a byproduct of the Excel export. |

**Current state vs plan (honesty):** the engine today is **pure pandas + a
rules-based scorer**; DuckDB and ML (LightGBM/MLflow) are *planned*, not built.
**Live now:** Clerk auth + tenant isolation, persistence + Alembic migrations,
dashboard + demo + authenticated upload + run history, deployed on Render.

**Revised next increments (in order):**
1. **Close the trust path** — Clerk keys → real uploads work; DPIA before first
   real data; Sentry PII scrubbing. (The bottleneck: a business can't safely
   upload yet.)
2. **RBAC `Membership` model + accountant invite + Excel export.**
3. **Companies House enrichment** (counterparty risk feature): onboarding
   name→number via `/search/companies`; a daily **Render Cron** poll of
   `GET /company/{number}` reading `accounts.next_accounts.due_on`/`.overdue`,
   `confirmation_statement.next_due`/`.overdue`, `company_status`,
   `links.insolvency`/`links.charges`; a shared `company_signals` table (keyed by
   company number, joined per tenant); signals feed the risk score. Poll, don't
   stream. API key auth (free, 600 req/5 min). Mind the deprecated `accounts.next_*`
   fields and the overdue-processing-lag grace buffer.
4. **Phase 3 model + MLflow** — rules → logistic → LightGBM-if-it-earns-it, with
   the CH features now available; MLflow tracks the rolling-origin bake-off.

## 1. Product thesis (unchanged wedge)

> Late-payment risk + 13-week cash runway + explainable action planning for UK
> SMEs. Decision support, **not** regulated advice.

Target beachhead (narrowed): **UK B2B service businesses and freelancers with
invoice payment terms** — the segment that feels late-payment pain most and is
least served by accountant-centric tools like Float. Accountants are a
secondary, later channel, not the wedge.

## 2. Skills wired into this plan

Installed skills that are genuinely useful here (Expo/mobile skills are **out of
scope** — this is a web product):

| Skill | Used in | Purpose |
|---|---|---|
| `domain-modeling` | Phase 0/1 | Lock canonical entities + ubiquitous language → `CONTEXT.md` |
| `codebase-design` | Phase 1 | Design forecasting/risk/ingestion as deep, testable, AI-navigable modules |
| `tdd` | Phase 1 | Engine logic (label, date maths, dedup, leakage) written red-green |
| `anthropic-skills:xlsx` | Phase 1/2 | Bank CSV/XLSX ingestion, synthetic exports, CSV report export |
| `anthropic-skills:pdf` | Phase 2 (deferred) | Accountant-facing PDF report when it lands |
| `frontend-design` + `web-design-guidelines` + `vercel-react-best-practices` | Phase 2 | "Calm financial control room" dashboard; accessibility; Next.js perf |
| `github-actions-docs` | Phase 4 | CI quality gates |
| `claude-api` | §8.6 work | LLM action-brief summaries (after deterministic rules are trustworthy; latest Claude models) |
| `security-review` / `code-review` / `simplify` / `verify` / `run` | throughout | Verification workflow on financial-data code |
| `grilling` | optional | Stress-test this plan before committing to Phase 1 |

## 3. MVP scope (the wedge, and only the wedge)

**In:**
- CSV/XLSX upload of bank transactions + invoices, plus a synthetic demo dataset.
- 13-week weekly cash forecast (P50 point estimate first).
- Invoice/customer ranking by **expected cash at risk**.
- Deterministic, plain-English **action brief**.
- One scenario toggle: "top customer pays 30 days late".

**Deferred (explicitly out of MVP):**
VAT/tax reserve estimation · anomaly & duplicate detection · the full six-scenario
planner · PDF export · P10/P90 confidence bands & conformal intervals · open-
banking / accounting connectors · LLM-written briefs.

## 4. Phased plan (re-sequenced: validate → thin slice → deepen)

### Phase 0 — Validate the problem (gate before any engine work)
Goal: confirm real demand before building.
- Write a one-page product brief and a **paper mock-up of the action brief**.
- Interview **5 UK SME owners / freelancers / accountants**. Test the real
  question: *"would this output change a chasing decision you'd make this week?"*
- Lock the **risk taxonomy** and the **domain model** (`domain-modeling` skill).
- Pin the **late-payment label** definition (see §6).
- Draft privacy notice + "not regulated advice" wording.
- **Gate 1 (kill switch):** ≥3 of 5 interviewees confirm the pain is real and
  current tools are insufficient. If not, stop or pivot.

### Phase 1 — Analytics engine on credible synthetic data *(current focus)*
Goal: build the finance intelligence engine, test-first, before any UI.
- Canonical schema + pydantic entities (`domain/`).
- **Synthetic UK SME generator** (`datagen/`) built from a **latent mechanism**
  (per-customer payment health + shared macro factor) the model never sees;
  distributions anchored to GOV.UK Payment Practices benchmarks (see §5).
- As-of feature store (`features/`) — every feature carries a computed-at
  timestamp ≤ prediction time (leakage-safe).
- Recurring-payment detection; invoice ageing.
- **Forecast baselines** (`forecasting/`): deterministic-ledger forecast +
  seasonal-naive. (Deterministic ledger is the real baseline to beat.)
- Cash runway + minimum-reserve threshold; shortfall-event detection.
- Deterministic action-brief templates (`reporting/`).
- Tests for schema, date logic, label, dedup, forecast identities, leakage.
- **Deliverable:** repeatable generator, engine, baseline evaluation report.

### Phase 2 — Thin usable slice + trust foundations → validate usefulness
Goal: smallest demoable product, secured from day one.
- Next.js + shadcn dashboard: Overview → Forecast → Invoice risk → Action brief.
- Upload workflow + demo mode; CSV export.
- **Auth + tenant isolation + row-level checks from the start** (hosted auth
  provider, not hand-rolled).
- Sentry with PII scrubbing (`send_default_pii=False`, `before_send` redaction).
- **DPIA before the first real upload** (sole-trader data is personal data).
- **Gate 2:** 3 users upload data and find one useful action in < 10 minutes.

### Phase 3 — Late-payment risk model (credible, not theatre)
Goal: turn the engine into defensible data science.
- Features from invoice/customer/payment history (as-of only).
- Companies House enrichment (**companies only, never sole-trader individuals**),
  GOV.UK payment-practices enrichment via as-of join.
- Rules baseline → logistic regression → LightGBM/XGBoost if it earns its keep.
- Probability calibration (isotonic/Platt on validation only).
- **Rolling-origin (walk-forward) evaluation**, group-aware splits, cold-start
  slice, pooled *and* per-SME metrics.
- **Gate 3:** beats the deterministic-ledger + seasonal-naive baselines on
  held-out data by a pre-declared margin (e.g. ≥10% pinball-loss reduction over
  ≥4 rolling origins; top-decile precision ≥ target), with calibration error
  below threshold. Validate distribution realism against GOV.UK benchmarks.

### Phase 4 — Production hardening
Goal: credible beyond a demo.
- Audit log; encrypted uploads (if any raw retention); export/delete account flow.
- No-sensitive-logs enforcement (test asserts no financial fields in logs).
- CSV-formula-injection defence on all exports.
- CI quality gates (`github-actions-docs`); threat model; security + privacy docs.
- **Gate 4:** ICO registration done; security README + threat model complete.

### Phase 5 — Real-user validation & monetisation experiment
Goal: external proof someone will pay.
- 5 users run it on **their own data**; measure time-to-insight; refine wording.
- Landing page + waitlist; single "would you pay £X?" question.
- **Gate 5:** ≥1 user runs it on their own data and asks to keep using it.

## 5. Synthetic data — the anti-circularity design (load-bearing)

The generator must produce data whose **generative assumptions differ from the
model's assumptions**, or the modelling proves nothing. Mandatory properties:

1. Per-customer **latent payment health** that persists across invoices
   (autocorrelation) — the model is *not* given it.
2. A shared **macro factor** (AR(1)) so late payments **cluster in time**.
3. **Right-skewed, heavy-tailed** payment-delay distribution (on-time mass +
   lognormal/Weibull tail), with a chase-cycle bump near `terms + 30`.
4. **Customer concentration** (power-law client sizes) — top 1–3 customers carry
   a large revenue share.
5. **Censoring**: the worst-health customers leave invoices unpaid at horizon.
6. **Seasonality + trend** (annual + month-end runs) per SME.
7. **Realistic obligation timing**: payroll, rent, VAT quarters, PAYE dates.
8. **Heteroscedastic noise** so calibration/intervals are non-trivial.
9. Messy-data realism for ingestion tests (dupes, bad dates, missing refs).
10. **Versioned, seeded, parameterised** generative DAG.

Anchor delay/late-rate distributions to **GOV.UK Payment Practices Reporting**
real data so the synthetic world is plausible, not invented.

## 6. The late-payment label (pinned now)

- **Prediction origin:** invoice issue date. **Horizon:** configurable T.
- **Target:** `paid > X days after due date OR unpaid at horizon T`. Report
  multiple thresholds (X ∈ {0, 14, 30}); default "late" = paid after due date.
- **Censoring:** unpaid-at-T counts as positive (worst payers are exactly the
  still-unpaid). Phase 3 may upgrade to a discrete-time **survival/hazard** model.
- **Leakage rule:** `days_overdue` and the eventual payment date are **labels,
  never features**. Every feature is computed as-of ≤ issue date.

## 7. Evaluation discipline

- **Forecast:** pinball/quantile loss (primary) + empirical interval coverage +
  **shortfall-event** precision/recall/lead-time; MAE secondary; report
  per-week-ahead (1…13), not pooled.
- **Risk:** PR-AUC vs prevalence baseline, top-decile precision tied to a
  realistic chase capacity (~10 invoices/week), calibration error.
- **Protocol:** rolling-origin backtest; group-aware (no customer in train+test);
  cold-start slice; pooled + per-SME; fixed seeds + versioned generator.

## 8. Decision gates (with teeth)

1. **Problem real?** ≥3/5 interviews confirm pain + tool gap. *(Phase 0, hard.)*
2. **MVP useful?** 3 users find one useful action in < 10 min. *(Phase 2.)*
3. **Model credible?** Beats baselines on held-out data by a pre-declared,
   quantified margin, calibrated. *(Phase 3.)*
4. **Production-credible?** ICO done, security README + threat model complete.
5. **Commercial pull?** ≥1 user runs it on their own data and asks to continue.

## 9. Reference anchors

- GOV.UK Payment Practices Reporting (real late-payment benchmark data).
- Making Tax Digital for Income Tax — phased from 6 Apr 2026 (readiness framing
  only; **never** build toward HMRC submission without recognition regime).
- FCA open banking (16m+ users) — connectors deferred to Phase 3+ via a
  regulated provider (rely on their authorisation; we are not an AISP).
- Small Business Commissioner — late payments cost UK SMEs ~£11bn/year.
- Companies House Public Data API (free; API-key over HTTP Basic; 600 req/5 min;
  poll, don't stream for MVP). Used for **counterparty (customer) risk
  enrichment** — limited companies + LLPs only; **sole traders/freelancers are not
  registered there**. Company profile gives statutory deadlines + overdue flags +
  insolvency/charges links in one call. Never profile sole-trader individuals.
