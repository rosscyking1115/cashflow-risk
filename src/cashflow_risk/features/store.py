"""As-of feature store for late-payment risk.

Given a set of invoices and a reference date ``as_of``, produces one
:class:`InvoiceFeatures` per invoice still open at ``as_of``. Every feature is
derived only from information observable at or before ``as_of`` — a customer's
*prior settled* invoices and the invoice's own terms and current ageing. The
eventual payment date of the invoice being scored is never consulted, so these
features are safe to use both for live scoring and for leakage-free training.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from cashflow_risk.domain import Invoice


@dataclass(frozen=True)
class InvoiceFeatures:
    """Leakage-safe features for one open invoice at a point in time."""

    invoice_id: str
    customer_id: str
    as_of: date
    amount: float
    terms_days: int
    days_overdue_now: int
    customer_prior_count: int
    customer_late_rate: float
    customer_avg_overdue: float
    is_cold_start: bool


def _is_open_at(invoice: Invoice, as_of: date) -> bool:
    if invoice.issue_date > as_of:
        return False
    return invoice.paid_date is None or invoice.paid_date > as_of


def _settled_by(invoice: Invoice, as_of: date) -> bool:
    return invoice.paid_date is not None and invoice.paid_date <= as_of


def build_invoice_features(
    invoices: Sequence[Invoice], as_of: date
) -> list[InvoiceFeatures]:
    history: dict[str, list[Invoice]] = {}
    for inv in invoices:
        if _settled_by(inv, as_of):
            history.setdefault(inv.customer_id, []).append(inv)

    features: list[InvoiceFeatures] = []
    for inv in invoices:
        if not _is_open_at(inv, as_of):
            continue

        prior = [p for p in history.get(inv.customer_id, []) if p.id != inv.id]
        prior_count = len(prior)
        if prior_count:
            overdues = [max(0, (p.paid_date - p.due_date).days) for p in prior]  # type: ignore[operator]
            late_rate = sum(1 for d in overdues if d > 0) / prior_count
            avg_overdue = sum(overdues) / prior_count
        else:
            late_rate = 0.0
            avg_overdue = 0.0

        features.append(
            InvoiceFeatures(
                invoice_id=inv.id,
                customer_id=inv.customer_id,
                as_of=as_of,
                amount=float(inv.amount),
                terms_days=(inv.due_date - inv.issue_date).days,
                days_overdue_now=max(0, (as_of - inv.due_date).days),
                customer_prior_count=prior_count,
                customer_late_rate=late_rate,
                customer_avg_overdue=avg_overdue,
                is_cold_start=prior_count == 0,
            )
        )
    return features
