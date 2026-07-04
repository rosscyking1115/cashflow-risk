# Production Readiness Plan — confidential company data

> Status: **decisions locked** (grilled 2026-07-04). This plan takes the project
> from *portfolio-grade* (boundaries **documented**) to a *production system for
> confidential company data* (boundaries **enforced**). It deepens and supersedes
> the "Phase 4 — Production hardening" bullet in [PLAN.md](PLAN.md). Companion docs:
> [threat-model.md](threat-model.md), [security_privacy.md](security_privacy.md),
> [dpia.md](dpia.md).

## 0. Locked decisions & roadmap (grilled 2026-07-04)

Outcome of the production-pivot grilling. Where these differ from §3–§5 below, these win.

| # | Decision | Choice |
|---|---|---|
| Q1 | End-state | **Multi-tenant SaaS, pilot-scale** (1–5 design-partner tenants first; billing/growth deferred) |
| Q2 | Delivery architecture | **Keep the split** — Python engine → FastAPI → Next.js client (already so) |
| Q3 | Tenant isolation | **Shared DB + Postgres RLS** as a second wall behind `repository.py` |
| Q4 | Identity | **Clerk, mandatory in prod** (fail closed, drop HS256, MFA); authz stays in-app (`Membership`) |
| Q5 | Ingestion | **Xero/QuickBooks connectors are the strategic core; hardened CSV upload bridges day-one & stays as permanent fallback** |
| Q6 | Compliance | **Compliant from day one** — EU/UK region, payload+token encryption + KMS, ICO + DPAs + DPIA sign-off before real data |
| Q7 | v1 scope | **The existing CSV→action-brief loop, made production-safe (Tier 0)** — no new features |
| Q8 | License & repo | **Proprietary; public now for portfolio, product repo goes private at go-live** |

**Follow-on defaults (adjustable):** async = keep the daily cron, add a queue only for connector syncs · storage = Postgres-only + a KMS/secret vault (no object store yet) · hosting = Render paid, EU/Frankfurt, Postgres w/ PITR (no native KMS → external key) · billing = Stripe, later · observability = wire Sentry + uptime + secret-scan CI step · repo = proprietary monorepo, private at go-live.

### Target architecture

```
 Browser ──Clerk session──> Next.js (Render, EU) ──Bearer JWT──> FastAPI (Render, EU)
                                                          │  authz: Membership/RBAC
                                                          ├──> Postgres (EU, PITR): RLS + envelope-encrypted payload
                                                          ├──> KMS / secret vault (wraps data keys, holds OAuth tokens)
                                                          ├──> Companies House API (outbound, read)
                                                          ├──> Xero/QuickBooks OAuth (fast-follow; tokens encrypted)
                                                          └──> Sentry (PII-scrubbed)
```

### Phased roadmap

- **Phase 0 — Foundations (free, reversible, do now):** record ADRs D1–D4; make
  auth fail-closed (Clerk-only in prod, no HS256); scaffold RLS; wire Sentry +
  uptime + a secret-scan CI step. No spend, strictly-better hardening.
- **Phase 1 — Tier 0 infra (on go-live trigger):** Render paid + EU region;
  Postgres with PITR + a tested restore drill; DB least-privilege role; envelope
  encryption of `analysis_runs.payload` behind a KMS; secrets moved to a vault;
  per-tenant rate limiting.
- **Phase 2 — Compliance & legal:** ICO registration + fee; DPAs (Clerk, Render,
  Sentry); DPIA sign-off; ROPA; confirm notice/retention match reality.
- **── Production Gate ──** a real customer's ledger can be uploaded, encrypted,
  DB-isolated, recovered from backup, audited, exported, and deleted — Clerk-only,
  EU region, signed DPIA — proven by tests + one restore/delete drill. **Take the
  product repo private here.**
- **Phase 3 — Connectors:** Xero/QuickBooks OAuth (app review, encrypted token
  storage + rotation, scheduled sync queue); CSV upload remains the fallback.
- **Phase 4 — Tier 1 scale/assurance:** immutable/streamed audit sink, per-tenant
  keys, pen test, on-call, SLA, load/DoS testing. Only with paying pull.

**Trigger for Phase 1+ spend:** a design partner (Gate 1/5) willing to put real
data in. Phase 0 is unconditional; Phases 1–2 wait for that partner (see §7).

## 1. Objective and principle

**Objective:** be able to safely and lawfully accept a real UK business's invoice
ledger — commercially sensitive data, and personal data where customers are sole
traders — and hold, process, and delete it to a standard we'd stake the company on.

**Principle:** *enforce, don't document.* Every boundary that today lives in a doc
or a code comment must become a control that fails closed — checked by the
platform, the database, or a test — not a promise.

## 2. Honest current posture

The engineering is mature; the **operational trust envelope is not yet closed**.

| Control | Portfolio-grade today | Production need |
|---|---|---|
| Identity | Clerk RS256 verification **exists**, but prod **silently falls back to HS256** if `CLERK_JWKS_URL` is unset; boot only refuses on the *default* secret | Clerk hard-required in prod (fail closed); MFA available; no HS256 in prod |
| Tenant isolation | Enforced in `repository.py` (app layer), tested | Keep — **plus** Postgres Row-Level Security as defense-in-depth (DB refuses cross-tenant even if app has a bug) |
| Data at rest | Managed-Postgres disk encryption; the sensitive `analysis_runs.payload` is **plaintext JSON** | Documented KMS; application-level encryption of the sensitive payload with a managed key |
| Data residency | Undecided (DPIA R4) | Pinned UK/EEA region, recorded |
| Backups / recovery | Whatever the free DB plan gives; **never tested** | Paid DB with PITR; a **tested** restore runbook |
| Secrets | Plaintext env vars; manual rotation | Managed secrets; documented rotation; no secret in logs (already enforced) |
| Audit trail | Append-only, but **user-erasable** with the account | Reconcile erasure vs. tamper-evident retention (see D4) |
| Abuse / DoS | No per-tenant rate limiting (threat model D2) | Application-level rate limiting + platform WAF |
| Hosting | Render **free tier** — sleeps, shared, no SLA | Paid tier with health/SLA; the cron already needs `starter` |
| Model claims | Not validated on real data (Gate 3 unmet on synthetic) | No predictive claims to customers until validated on real data |

## 3. Decisions to lock first (ADRs)

Each is load-bearing; record as an ADR under `docs/adr/`. My recommendation in bold.

- **D1 — Identity provider & fallback.** Keep Clerk. **Make Clerk mandatory in
  production**: refuse to boot if `is_production()` and `CLERK_JWKS_URL` is unset;
  remove the HS256 path from the prod code path (HS256 stays dev/test only).
  Enforce MFA for owners via Clerk policy.
- **D2 — Hosting & data residency.** **Stay on Render but on paid tiers, pinned to
  an EU/UK region** (Frankfurt) for the API, web, and Postgres; record the region
  decision to satisfy DPIA R4. (Re-evaluate a UK-region provider only if a customer
  contractually requires UK-only.)
- **D3 — Encryption of the sensitive payload.** **Application-level encryption of
  `analysis_runs.payload`** (envelope encryption: a data key per row wrapped by a
  KMS master key), so a database dump alone never exposes a customer's ledger.
  Key in a managed KMS/secrets store, not env.
- **D4 — Audit vs. erasure.** Resolve the tension: a customer's *personal* audit
  entries are erased with their account (GDPR), but keep a **separate, minimal,
  non-personal security-event log** (tenant id hash + action + time, no content)
  that is append-only and retained for incident forensics. Document the basis.

## 4. Workstreams

Tasks are test-first and keep the standards (uv/pytest, ruff, mypy-strict, clean
web build, Alembic migration on schema change).

**WS-A — Identity & access (fail closed)**
- Prod refuses to boot without Clerk (extend the `lifespan` guard in `api/app.py`).
- Drop the HS256 branch from `require_principal` when `is_production()`.
- MFA policy in Clerk; session/expiry review; accountant-invite SSO story.
- Add Postgres RLS policies keyed to a per-request `SET app.business_id`, as a
  second wall behind `repository.py` (supabase-postgres-best-practices pattern).

**WS-B — Data governance & storage**
- Envelope-encrypt `analysis_runs.payload` (transparent encrypt/decrypt at the
  repository boundary; Alembic migration to the encrypted column).
- DB least-privilege: the app role can CRUD its tables, not superuser.
- Backups: enable PITR; write and **execute** a restore drill; record RPO/RTO.
- Confirm data-minimisation still holds end to end (no raw upload persisted).

**WS-C — Secrets & key management**
- Move JWT/Clerk/CH/KMS secrets into a managed store; document rotation.
- Verify no secret ever reaches logs/Sentry (already test-enforced — extend the
  assertion to the new KMS keys).

**WS-D — Reliability & operations**
- Paid hosting tiers, EU region, health checks, uptime/alerting (wire `SENTRY_DSN`;
  add uptime monitoring).
- Application rate limiting per tenant/IP (closes threat-model D2).
- Incident-response runbook + breach-notification process (72-hour ICO clock).
- Dependency/secret scanning in CI (Dependabot done; add a SAST/secret-scan step).

**WS-E — Compliance & legal**
- ICO registration + fee paid; DPIA signed off (R4/R5 closed by D2 + DPAs).
- Processor DPAs executed (Clerk, Render, Sentry) and sub-processor list recorded.
- Records of processing (ROPA); confirm privacy notice + retention match reality.

**WS-F — Product-truth gate**
- No predictive/accuracy claims in-product or in marketing until the risk model is
  validated on real data against the pre-declared Gate 3 margin. Until then the UI
  frames outputs as rules-based estimates (already the case).

## 5. Sequencing — two tiers

Full production-grade for confidential data is expensive, and **the product has not
passed Gate 1 (demand)**. Don't build the whole thing before there's pull. Stage it:

**Tier 0 — Pilot-safe (accept the first ≤5 design partners' real data).**
The minimum to lawfully and safely onboard *one* real business. Blocks the first
real upload.
- D1 (Clerk mandatory + MFA), D2 (EU region + paid DB), D3 (payload encryption),
  D4 (audit basis) decided.
- WS-A fail-closed auth + RLS · WS-B payload encryption + tested backup · WS-C
  secrets moved · WS-D rate limiting + Sentry live + incident runbook · WS-E ICO
  fee + DPAs + DPIA sign-off.
- **Production Gate (definition of done):** a real customer's ledger can be
  uploaded, encrypted at rest, isolated at the DB layer, recovered from backup,
  audited, exported, and deleted — with Clerk-only auth, in an EU region, under a
  signed DPIA. Verified by tests + one documented restore/delete drill.

**Tier 1 — Scale & assurance (only when there's paying pull).**
Immutable/streamed audit sink, per-tenant keys, SOC 2-lite controls, formal
pen test, on-call rotation, load/DoS testing, SLA. Deferred deliberately.

## 6. Parallelisation (where agents help)

Once §3 decisions are locked, WS-A/B/C/D/E are largely independent and suit
concurrent subagents (dispatching-parallel-agents): e.g. one agent per workstream
against a shared decisions doc, each opening a focused PR. WS-A and WS-B share the
repository/DB layer, so sequence those two or coordinate on `repository.py`.

## 7. The honest caveat

This plan is correct *engineering*; whether to spend it now is a *founder* call.
The demand-first thesis (PLAN.md §0) says validate before building. The pragmatic
read: do **Tier 0 only when interviews (Gate 1) point to a design partner willing
to put real data in** — Tier 0 is precisely what unblocks Gate 5 ("someone runs it
on their own data"). Building Tier 1 before that is the trap this project was
restructured to avoid.
