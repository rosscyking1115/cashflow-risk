"""Couple late-payment risk into the cash forecast.

The forecast needs, per invoice, an expected payment delay (days after due date).
Rather than a flat assumption, we derive it from the same risk view the ranking
uses, so the two tell one story:

- **Known customers** are timed from their *observed* history — the mean days
  overdue already blends how often and how late they pay. This is the most
  defensible signal we have.
- **Cold-start customers** (no history) fall back to ``probability × a default
  late delay``, so a riskier-looking new invoice is expected later.

An invoice already overdue at ``as_of`` is never expected to be paid earlier
than it already is.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from cashflow_risk.domain import Invoice
from cashflow_risk.features.store import InvoiceFeatures
from cashflow_risk.risk.baseline import score_late_probability

DEFAULT_LATE_DELAY_DAYS = 30


def expected_delay_days(features: InvoiceFeatures, probability: float) -> int:
    """Expected days an invoice is paid after its due date, for forecasting."""
    if features.is_cold_start:
        base = probability * DEFAULT_LATE_DELAY_DAYS
    else:
        base = features.customer_avg_overdue
    return max(features.days_overdue_now, round(base))


def risk_adjusted_delay_fn(features: Iterable[InvoiceFeatures]) -> Callable[[Invoice], int]:
    """Build a per-invoice delay function for ``forecast_cash``.

    Scores each invoice once and returns a lookup by invoice id; invoices with no
    computed features default to 0 (paid on the due date).
    """
    delays = {
        f.invoice_id: expected_delay_days(f, score_late_probability(f).probability)
        for f in features
    }
    return lambda invoice: delays.get(invoice.id, 0)
