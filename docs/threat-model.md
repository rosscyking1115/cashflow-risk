# Threat model

Scope: the Cashflow Risk Intelligence service — the FastAPI engine, the Next.js
dashboard, and the managed Postgres store. Method: STRIDE over the data-flow
below. This is a living document; revise it on any change to data, trust
boundaries, processors, or authentication. Companion docs:
[security_privacy.md](security_privacy.md), [dpia.md](dpia.md).

## 1. System and data flows

```
 Browser ──TLS──> Next.js dashboard ──TLS + Bearer JWT──> FastAPI engine ──> Postgres
   │  (Clerk sign-in)                    │                     │
   │                                     ├──> Companies House Public Data API (read)
   │                                     └──> Sentry (errors, PII-scrubbed)
```

Trust boundaries (where data crosses a privilege level):

- **B1 Browser → API.** Every `/api/*` call except the demo and health is
  authenticated with a Bearer JWT. The tenant (`business_id`) is derived from the
  verified token and the `X-Business-Id` header checked against memberships —
  never taken from unauthenticated client input.
- **B2 API → Postgres.** All tenant data is reached through `repository.py`, which
  scopes every query by `business_id`.
- **B3 API → Companies House.** Outbound, read-only, keyed by an API key. Only
  company numbers (public identifiers) leave the system; never tenant financials.
- **B4 API → Sentry.** Outbound error reports, scrubbed of PII and bodies.

## 2. Assets

| Asset | Sensitivity |
|---|---|
| Uploaded invoice ledgers (amounts, counterparty names, incl. sole-trader personal data) | High — personal + commercially sensitive |
| Persisted analysis results (`analysis_runs.payload`) | High — derived from the above |
| Auth secrets (`CASHFLOW_JWT_SECRET`, Clerk keys, `COMPANIES_HOUSE_API_KEY`, `DATABASE_URL`) | Critical |
| Membership / invitation graph (who can see whose data) | High — governs access |
| Audit trail | Medium — integrity matters |
| Companies House signal cache | Low — public-register data |

Data minimisation: raw uploads are **not** stored — only derived results are
persisted (see [security_privacy.md](security_privacy.md)).

## 3. STRIDE

| # | Threat | Vector | Mitigation | Status |
|---|---|---|---|---|
| S1 | **Spoofing** a tenant | Forged/replayed JWT | PyJWT verification — HS256 with a required secret in dev, Clerk JWKS (RS256, issuer-checked) in prod; 1-hour expiry; missing-claim rejection | Built |
| S2 | Dev-token endpoint abused in prod | `/api/auth/dev-token` mints tenant tokens | Secure-by-default: disabled unless `CASHFLOW_ENV=dev` or an explicit opt-in flag; returns 404 otherwise | Built |
| S3 | Server boots with the insecure default secret | Misconfiguration | Startup **refuses to boot** in production while the default JWT secret is in use | Built |
| T1 | **Tampering** — cross-tenant read/write | Guessed run/business id, or a forged `X-Business-Id` | `repository.py` scopes every query by `business_id`; `get_run` matches on both id *and* tenant; the active business is authorised against the membership graph | Built (tested, incl. cross-tenant refusal) |
| T2 | Privilege escalation | A read-only accountant uploads or mutates | Role check: only `OWNER` may upload; owner-only guards on rename/invite/member endpoints | Built |
| R1 | **Repudiation** — deny an action | No record of who did what | Append-only, tenant-scoped audit log (`run.create/export`, `account.export`, `member.*`, `business.rename`), attributed to the acting user | Built |
| I1 | **Information disclosure** in logs/errors | Financial data in log lines or Sentry events | No-sensitive-logs test; Sentry `send_default_pii=False`, no locals, no bodies, `before_send` redaction | Built (test-enforced) |
| I2 | Disclosure via exports | CSV-formula injection in an opened export | `=+-@` cells prefixed on every export | Built |
| I3 | Disclosure at rest / in transit | Network capture, DB theft | TLS everywhere; managed Postgres encryption at rest; secrets in env, generated JWT secret | Built (infra) |
| I4 | Over-collection of third-party PII | Profiling individuals via Companies House | CH enrichment is companies + LLPs only; sole-trader individuals are never looked up | Built |
| D1 | **Denial of service** via upload | Oversized / high-row / parser-bomb file | 5 MB streamed size limit, 50k row limit, content sniffing; XLSX rejected (no zip/XML parser on the path) | Built |
| D2 | Resource exhaustion | Request floods | Platform-level; a per-tenant rate limit is a known gap (§5) | Partial |
| E1 | **Elevation** via CORS/CSRF | Malicious origin calls the API with a user's creds | Bearer-token auth (not cookies) → not ambient; CORS allow-list / regex; credentials not required | Built |

## 4. Data lifecycle controls

- **Erasure (R6):** self-serve `DELETE /api/account` erases the tenant's runs,
  audit events, memberships (both directions), invitations, and business row.
- **Retention:** results and audit events older than 24 months are auto-purged
  by the daily maintenance job.
- **Portability:** `GET /api/account/export` returns everything held as JSON.

## 5. Residual risks and known gaps

- **No per-tenant API rate limiting** (D2) — rely on platform limits for MVP;
  add application-level throttling before scale.
- **Operational conditions before real data** (tracked in the DPIA, not code):
  UK/EEA hosting-region decision (R4), processor DPAs (R5), ICO fee.
- **Secret rotation** is manual (platform env vars); no automated rotation yet.
- **Companies House signals are cached**; a company's status can be stale between
  daily refreshes (accepted — filings change slowly; overdue uses a grace buffer).

## 6. Assumptions

- The hosted IdP (Clerk) and platform (Render, managed Postgres) are trusted
  processors under DPAs; their compromise is out of scope here (covered by
  processor due diligence in the DPIA).
- TLS is terminated by the platform; the app assumes HTTPS end to end.
