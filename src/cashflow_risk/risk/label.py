"""The pinned late-payment label.

- **Prediction origin:** the invoice issue date.
- **Horizon T:** configurable; the label is resolved as-of ``horizon``.
- **Target:** paid more than ``days_threshold`` days after the due date, OR still
  unpaid at the horizon. An invoice unpaid at T is a *positive* — the worst payers
  are exactly the ones still outstanding (censoring handled, not dropped).

``days_overdue`` and the eventual payment date are the label, never features
(leakage rule). Features are built strictly as-of the issue date elsewhere.
"""

from __future__ import annotations

from datetime import date

from cashflow_risk.domain import Invoice


def late_label(invoice: Invoice, *, horizon: date, days_threshold: int = 0) -> bool:
    """Whether ``invoice`` is a late-payment positive, resolved as-of ``horizon``.

    Paid on/after the horizon counts as *unpaid as-of the horizon*, so a payment
    we could not yet have observed never leaks a "settled" outcome into the label.
    """
    paid = invoice.paid_date
    if paid is not None and paid <= horizon:
        return (paid - invoice.due_date).days > days_threshold
    return True  # unpaid at the horizon -> positive
