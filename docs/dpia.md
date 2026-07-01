# Data Protection Impact Assessment (DPIA) — draft

> **Status: draft template.** Complete the `[bracketed]` fields and have it
> reviewed by a data-protection adviser before processing real customer data.
> This is not legal advice. A DPIA is required under UK GDPR Art. 35 because the
> product carries out **systematic profiling** (late-payment risk scoring) of
> data that includes personal data (sole traders are natural persons).

- **Controller:** [your legal entity / name], [address], ICO registration [ref]
- **DPO / contact:** [name, email]
- **Product:** Cashflow Risk Intelligence — late-payment risk + 13-week cash runway
- **Date / version:** [date] / v0.1 · **Next review:** on any material change

## 1. Describe the processing

**What & why.** A UK SME (or their invited accountant) uploads invoice data. The
service parses it, scores each invoice/customer for late-payment risk, forecasts
13 weeks of cash, and produces a plain-English action brief. Purpose: help the
SME decide which invoices to chase to protect their cash runway. **Decision
support only — not a credit decision, not regulated advice.**

**Data processed.**
- *User account:* name, email, auth identifiers (via Clerk).
- *Uploaded invoices:* invoice ids, amounts, dates, and **customer identifiers**
  (business or, sometimes, an individual sole trader's name) + payment history.
- *Derived:* risk scores, cash forecasts, action briefs (stored as run snapshots).
- **Not stored:** raw upload files — parsed in memory and **discarded after parse**;
  only derived entities persist.

**Data subjects.** (a) the SME user; (b) the SME's **customers** named on invoices
— including sole traders (natural persons) who have **not** interacted with us.

**Scope & context.** Volume: one SME's data is small (KBs). Sensitivity: financial
(not special-category). The customer-profiling of third parties is the key
sensitivity. Retention: derived run snapshots kept until the user deletes them or
account closure; default auto-purge [define window]. Processors: **Clerk** (auth),
**Render** (hosting + managed Postgres).

**Flows.** Browser → API (Clerk-verified) → engine → Postgres (derived results
only). Tenant-isolated per business; role-based access (owner read+write,
accountant read-only).

## 2. Consultation

- Data subjects: [SME interviewees — Phase 0]. Customers (third parties) are not
  directly consulted; their interests are addressed by the measures in §5.
- Processors' terms/DPAs reviewed: Clerk [link], Render [link]. [status]

## 3. Necessity & proportionality

- **Lawful basis:** performance of a contract with the user (Art. 6(1)(b)) for
  their own data; **legitimate interests** (Art. 6(1)(f)) for processing customer
  identifiers to compute the risk the user asked for — balanced by using
  **first-party data only** (the user's own payment history with that customer).
- **No Art. 22 solely-automated decision** with legal/significant effect: scores
  are advisory, surfaced with drivers and a "why", and the human user acts on them.
  We never make an automated credit/creditworthiness decision about any individual.
- **Data minimisation:** raw files discarded after parse; only derived results
  stored; no external credit-style enrichment on individuals.
- **Third-party (customer) profiling** is the highest-scrutiny processing — see §5.

## 4. Risks to individuals

| # | Risk | Likelihood | Severity |
|---|---|---|---|
| R1 | A **customer** (esp. a sole trader) is profiled for "late payment" without their knowledge/consent | Medium | Medium |
| R2 | Financial data exposed via a breach or a cross-tenant access flaw | Low | High |
| R3 | Financial data leaks into logs / error reports | Low | Medium |
| R4 | International transfer if data is hosted outside the UK/EEA (Render default region is US) | Medium | Medium |
| R5 | A processor (Clerk/Render) mishandles data | Low | Medium |
| R6 | A data subject can't exercise access/erasure | Low | Medium |
| R7 | Inaccurate score unfairly characterises a customer | Medium | Medium |

## 5. Measures to reduce risk

| Ref | Measure | Status |
|---|---|---|
| R1 | **First-party data only** — scores are framed "based on your payment history with this customer"; Companies House enrichment on **companies only, never sole-trader individuals**; no external credit data on individuals | Built (framing/wording); enforce in enrichment |
| R1 | Wording rules: never "this customer is unsafe"; always "estimate / planning support / review with your accountant" | Built |
| R2 | Auth (Clerk JWT), **tenant isolation** (every query scoped by business_id), **RBAC** (owner/accountant), tested incl. cross-tenant refusal | Built |
| R2 | Encryption in transit (HTTPS) + at rest (managed Postgres); secrets in env, generated JWT secret | Built |
| R3 | No raw financial data in logs; unhandled errors return generic messages; **enforced by test** (`tests/test_observability.py` uploads marker data and asserts none of it reaches any log record); Sentry configured with `send_default_pii=False`, no locals, no request bodies, `before_send` redaction (`src/cashflow_risk/observability.py`) | Built |
| R4 | **Host in a UK/EEA region** (Render Frankfurt) or put appropriate transfer safeguards (UK IDTA/addendum) in place; record the decision | **To do before real data** |
| R5 | Processor DPAs signed (Clerk, Render); sub-processor lists reviewed | To do |
| R6 | Self-serve **export** (Excel/CSV) + **delete** (account/data) controls; documented SAR process | Export built; add delete + SAR process |
| R7 | Every score shows drivers + uncertainty; rectification on request; human always in the loop | Built (explainable scores) |

## 6. Sign-off & outcome

- **Residual risk:** [Low / Medium] after measures.
- **Outcome:** [Proceed / Proceed with conditions]. Conditions to close before
  processing real customer data: R4 (hosting region / transfer safeguards), R5
  (processor DPAs), R6 (delete flow + SAR), ICO fee paid. R3 (log-scrubbing +
  Sentry PII off) is built and test-enforced.
- **Approved by:** [name, role, date]. **Review:** on any change to data, purpose,
  processors, or the addition of connectors (open banking / accounting APIs).
