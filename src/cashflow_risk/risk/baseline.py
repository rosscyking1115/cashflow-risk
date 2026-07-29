"""Rules-based late-payment risk baseline.

A deliberately transparent scorer (rules and a logistic form before any
gradient boosting). It combines leakage-safe features into a log-odds score, maps
it to the 0–1 range, and records the drivers behind it so every score has a
plain-English "why". This is the baseline any fitted model must beat on
held-out *real* data — synthetic performance proves nothing (docs/adr/0002).

The 0–1 output is a **ranking score, not a calibrated probability**: measured mean
ECE 0.186 on purged folds (0.212 with Companies House signals), systematically
over-predicting lateness. It orders invoices correctly enough to drive a chase
list; it does not tell you the odds.
Calibrating it (isotonic or Platt, fitted on a purged fold) is unfinished work.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from cashflow_risk.enrichment.companies_house import (
    CompanySignals,
    filing_risk_drivers,
    filing_risk_logit,
)
from cashflow_risk.features.store import InvoiceFeatures

# Interpretable log-odds weights. Tunable; not fitted (this is the rules baseline).
_INTERCEPT = -1.0
_W_LATE_RATE = 2.2  # a customer's prior late rate is the strongest signal
_W_OVERDUE_NOW = 0.03  # already-overdue invoices are likelier to stay late
_W_AVG_OVERDUE = 0.004  # chronically slow payers
_W_LONG_TERMS = 0.01  # longer terms drift later
_COLD_START_PENALTY = 0.4  # mild upward nudge under no history

_HIGH = 0.6
_MEDIUM = 0.35


@dataclass(frozen=True)
class RiskScore:
    """An explainable late-payment risk score for one invoice."""

    invoice_id: str
    customer_id: str
    probability: float
    band: str  # "low" | "medium" | "high"
    cash_at_risk: float
    drivers: list[str]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _band(p: float) -> str:
    if p >= _HIGH:
        return "high"
    if p >= _MEDIUM:
        return "medium"
    return "low"


def score_late_probability(
    f: InvoiceFeatures, signals: CompanySignals | None = None
) -> RiskScore:
    logit = _INTERCEPT
    logit += _W_LATE_RATE * f.customer_late_rate
    logit += _W_OVERDUE_NOW * f.days_overdue_now
    logit += _W_AVG_OVERDUE * f.customer_avg_overdue
    logit += _W_LONG_TERMS * max(0, f.terms_days - 30)
    if f.is_cold_start:
        logit += _COLD_START_PENALTY
    if signals is not None:
        logit += filing_risk_logit(signals)

    probability = _sigmoid(logit)

    drivers: list[str] = []
    # Companies House signals first — they're the strongest, most concrete drivers.
    if signals is not None:
        drivers.extend(filing_risk_drivers(signals))
    if f.customer_late_rate > 0:
        drivers.append(
            f"Customer has paid late {f.customer_late_rate:.0%} of the time "
            f"({f.customer_prior_count} prior invoices)"
        )
    if f.days_overdue_now > 0:
        drivers.append(f"Already {f.days_overdue_now} days overdue")
    if f.is_cold_start:
        drivers.append("No payment history with this customer yet")
    if f.terms_days >= 60:
        drivers.append(f"Long payment terms ({f.terms_days} days)")
    if not drivers:
        drivers.append("Consistent on-time payment history with this customer")

    return RiskScore(
        invoice_id=f.invoice_id,
        customer_id=f.customer_id,
        probability=probability,
        band=_band(probability),
        cash_at_risk=f.amount * probability,
        drivers=drivers,
    )


def rank_by_cash_at_risk(
    features: Iterable[InvoiceFeatures],
    company_signals: dict[str, CompanySignals] | None = None,
) -> list[RiskScore]:
    """Score invoices and order them by expected cash at risk, highest first.

    ``company_signals`` maps a customer's Companies House number to its signals;
    an invoice is enriched when its customer's number is present.
    """
    signals = company_signals or {}
    scores = [
        score_late_probability(f, signals.get(f.company_number) if f.company_number else None)
        for f in features
    ]
    scores.sort(key=lambda s: s.cash_at_risk, reverse=True)
    return scores
