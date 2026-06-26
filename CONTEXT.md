# Cashflow Risk Intelligence

The domain language for a tool that forecasts a UK SME's short-term cash position
and ranks the late payments that threaten it. This file is the glossary — the
shared vocabulary. It holds no implementation detail.

## Language

### Core entities

**Business**:
The UK SME that owns the data and uses the tool. The unit of tenancy — all data
belongs to exactly one Business.
_Avoid_: company, tenant, organisation, user (a User is a login, not the Business).

**Account**:
A bank account held by the Business, with a running balance.
_Avoid_: wallet, ledger.

**Transaction**:
A single dated money movement on an Account — an inflow or an outflow that has
already happened.
_Avoid_: entry, line, payment (a payment is what settles an Invoice; a
Transaction is the bank record of it).

**Invoice**:
Money owed **to** the Business by a Customer, with an issue date, due date, and
payment terms. A receivable.
_Avoid_: bill (that is the opposite direction), sales invoice, receivable.

**Bill**:
Money the Business owes **to** a Supplier. A payable.
_Avoid_: invoice (reserved for receivables), expense, payable.

**Customer**:
A party the Business sends Invoices to.
_Avoid_: client, buyer, debtor, account.

**Supplier**:
A party that sends the Business Bills.
_Avoid_: vendor, creditor, payee.

**Tax obligation**:
A scheduled payment to HMRC (VAT, PAYE, etc.) with a known due date. A
deterministic future outflow.
_Avoid_: tax bill, liability.

**Recurring event**:
A detected pattern of regular inflow or outflow (e.g. monthly rent, weekly
payroll) inferred from history.
_Avoid_: subscription, schedule.

### Risk & forecast concepts

**Payment terms**:
The agreed number of days after an Invoice's issue date by which a Customer
should pay (e.g. "30 days").
_Avoid_: net terms, credit period.

**Due date**:
Issue date plus Payment terms. The date an Invoice is expected to be paid.

**Late payment**:
An Invoice paid after its Due date, or still unpaid at the forecast horizon. The
prediction target. Defined at issue time; "days overdue" is an outcome, never an
input to prediction.
_Avoid_: overdue (used for the *state*, not the label), delinquency.

**Ageing**:
How long an unpaid Invoice has been outstanding relative to its Due date.
_Avoid_: aged debt.

**Cash at risk**:
The expected dueamount exposed to lateness — an Invoice's outstanding amount
weighted by its late-payment probability. The metric that ranks Invoices and
Customers.
_Avoid_: exposure, expected loss.

**Cash runway**:
The number of weeks until the Business's forecast cash balance falls below its
Minimum reserve threshold.
_Avoid_: burn, headroom.

**Minimum reserve threshold**:
The cash balance below which the Business is considered at risk (e.g. one
payroll run). The line a Shortfall crosses.
_Avoid_: buffer, floor.

**Shortfall**:
A forecast week in which the closing cash balance falls below the Minimum
reserve threshold. The event the tool exists to predict.
_Avoid_: deficit, gap.

**Customer concentration**:
The degree to which the Business's receivables depend on a few Customers — a risk
amplifier when one of them pays late.
_Avoid_: dependency, exposure.

**Forecast run**:
One execution of the forecast for a Business at a point in time, producing a
13-week weekly cash projection. Re-running later produces a new Forecast run;
they are not mutated.
_Avoid_: projection, simulation, scenario (a scenario is a what-if *variant* of a
Forecast run).

**Risk signal**:
A flagged, explainable risk attached to a Forecast run (e.g. "Shortfall in week
6") — always paired with a driver and a suggested action.
_Avoid_: alert, warning, flag.

**Action brief**:
The plain-English output that explains the top Risk signals, their drivers, and
what the Business could do this week. Decision support, never advice.
_Avoid_: report, recommendation, advice.

**Audit event**:
An immutable record of a data import, export, sync, or deletion — for the
Business's own trust and traceability.
_Avoid_: log (logs are operational; an Audit event is domain-meaningful).
