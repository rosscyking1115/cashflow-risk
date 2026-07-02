# Security, Privacy & UK Regulatory Posture

Micro-SaaS-first means real businesses' real financial data. Trust is the
product. These constraints are not optional.

## Principles

- **Data minimisation.** Raw uploads parsed server-side and **discarded after
  parse**; only derived entities persist. Default retention + auto-purge, not
  just a user toggle.
- **No raw financial data in logs or error reports.** Enforced, not aspirational
  (see below).
- **Encryption in transit and at rest**; export/delete account flow; audit trail
  for imports, exports, syncs, deletes.
- **No model training on customer data without explicit opt-in.**

## Enforcement (must exist before the first real upload)

- Sentry — **implemented** (`src/cashflow_risk/observability.py`):
  `send_default_pii=False`, `include_local_variables=False` (stack locals carry
  ledgers), `max_request_body_size="never"`, and `before_send` redaction of
  amounts, counterparty names, invoice/company fields, auth headers. Enabled
  only when `SENTRY_DSN` is set.
- A **test that asserts** no financial fields appear in log output —
  **implemented** (`tests/test_observability.py`: uploads marker data, captures
  all logs at DEBUG, asserts none of it appears; plus scrubber unit tests).
- Structured logging with an explicit allowlist of loggable fields (future — the
  log-hygiene test is the current backstop).
- **CSV-formula-injection defence** on every export: prefix cells beginning with
  `= + - @` (Excel/Sheets opens accountant exports — this is a real vector).
- File-upload hardening — **implemented** (`src/cashflow_risk/api/upload_guard.py`):
  5 MB size limit enforced while streaming (never buffers an oversized body),
  50k row limit, content sniffing (zip/xlsx magic bytes and binary content are
  rejected with a plain-English message; browser MIME headers are not trusted).
  XLSX uploads are not accepted at all — which is also the parser-bomb defence:
  no zip/XML parser exists on the upload path.
- **Auth + tenant isolation — implemented (request layer).** Real uploads
  (`/api/analyze`) require a verified JWT; the tenant `business_id` is taken from
  the token, never from client input, so a caller cannot act as another tenant.
  The demo endpoint is public (synthetic data only). Auth is a provider-agnostic
  JWT seam (`cashflow_risk.auth`) — a hosted IdP slots into token verification
  before launch. **Row-level DB access checks land with persistence** (Postgres),
  reusing the same `Principal` scope.
- Dev token minting is **disabled by default**; enabled only with `CASHFLOW_ENV=dev`
  or `CASHFLOW_ALLOW_DEV_TOKEN=1`. Production sets `CASHFLOW_JWT_SECRET`.

## UK regulatory posture

- **FCA / AISP:** open-banking connectors (Phase 3+) go through a regulated
  provider (TrueLayer/Yapily/Plaid). We rely on **their** authorisation as a
  technical service provider; **we are not an AISP** and never initiate payments,
  lend, or hold client money. State this explicitly; don't imply own permissions.
- **DPIA (UK GDPR Art. 35):** triggered by **first processing of real personal /
  financial data** — sole traders are natural persons, and late-payment risk
  scoring is "systematic profiling". So the DPIA is due **before the first real
  upload (end of Phase 2)**, *not* gated on connectors. Synthetic-only phases
  need no DPIA.
- **ICO registration / data-protection fee:** required as soon as we process real
  personal data as a controller. Cheap, mandatory, easy to forget — do it in
  Phase 4.
- **Making Tax Digital:** **readiness/record-tidiness only.** Never "filing".
  Becoming MTD-compatible software has its own HMRC recognition regime — do not
  drift into it.
- **Third-party profiling:** scoring *your customer's* late-payment likelihood
  profiles a third party who never consented. Mitigate: use **first-party data
  only** ("based on your payment history with this customer"); Companies House
  enrichment on **companies, never sole-trader individuals**; no external
  credit-style enrichment on individuals.

## Wording rules (UI + briefs)

**Use:** "cashflow risk estimate", "planning support", "based on your payment
history", "not accounting, tax, legal, credit, or investment advice", "review
with your accountant before acting".

**Never:** "you should borrow", "this customer is unsafe", "this is tax advice",
"approved credit decision".
