"""Leakage-safe training examples for the late-payment risk model.

Turns a set of invoices into one labelled example each, with the prediction
origin fixed at the invoice's **issue date**: features are built as-of that date
(so only prior-settled history is visible) and the label is resolved at
``issue_date + horizon_days`` (see :mod:`cashflow_risk.risk.label`).

This is the bridge between the raw ledger and the evaluation harness / any model.
It is deliberately offline and training-time only — no persistence, no tenant
scope — and never consults an invoice's eventual payment to build its features.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from cashflow_risk.domain import Invoice
from cashflow_risk.features.store import InvoiceFeatures, build_invoice_features
from cashflow_risk.risk.label import late_label


@dataclass(frozen=True)
class TrainingExample:
    """One invoice's as-of-issue features paired with its resolved late label."""

    features: InvoiceFeatures
    label: bool


def build_training_examples(
    invoices: Sequence[Invoice],
    *,
    horizon_days: int,
    days_threshold: int = 0,
    observed_until: date | None = None,
) -> list[TrainingExample]:
    """Build one leakage-safe, labelled example per invoice.

    Features for an invoice are computed as-of its issue date across the *whole*
    ledger (prior-settled invoices only), so a customer's history informs later
    invoices without any invoice seeing its own outcome.

    ``observed_until`` is the last date for which the ledger is complete. When
    given, invoices whose label horizon (``issue_date + horizon_days``) falls
    beyond it are dropped: their outcome is not yet observable, so counting a
    not-yet-resolved invoice as a "still unpaid" positive would be a censoring
    artifact rather than a true late payment. Omit it only for a ledger you know
    is fully resolved.
    """
    by_issue_date: dict[date, list[Invoice]] = {}
    for inv in invoices:
        by_issue_date.setdefault(inv.issue_date, []).append(inv)

    examples: list[TrainingExample] = []
    for issue_date, issued in by_issue_date.items():
        horizon = issue_date + timedelta(days=horizon_days)
        if observed_until is not None and horizon > observed_until:
            continue  # label not yet resolvable — skip to avoid censoring bias
        # Features as-of the issue date for every invoice open then; index by id
        # and pick out the ones actually issued on this date (their origin).
        as_of_features = {f.invoice_id: f for f in build_invoice_features(invoices, issue_date)}
        for inv in issued:
            features = as_of_features.get(inv.id)
            if features is None:  # not open at its own issue date (shouldn't happen)
                continue
            examples.append(
                TrainingExample(
                    features=features,
                    label=late_label(inv, horizon=horizon, days_threshold=days_threshold),
                )
            )
    return examples
