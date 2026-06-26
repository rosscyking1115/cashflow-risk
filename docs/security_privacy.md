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

- Sentry: `send_default_pii=False` + `before_send` redaction of amounts,
  counterparty names, invoice/transaction fields.
- Structured logging with an explicit allowlist of loggable fields.
- A **test that asserts** no financial fields appear in log/Sentry output.
- **CSV-formula-injection defence** on every export: prefix cells beginning with
  `= + - @` (Excel/Sheets opens accountant exports — this is a real vector).
- File-upload hardening: size/row limits, MIME validation, XLSX parser-bomb
  protection.
- Auth + tenant isolation + row-level access checks from Phase 2 (the public
  demo is multi-tenant the moment it exists).

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
