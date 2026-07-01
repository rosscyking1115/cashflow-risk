"""The pinned late-payment label (PLAN §6).

Prediction origin = issue date; horizon = configurable T. Target: paid > X days
after due date OR unpaid at horizon T (censored worst-payers count as positive).
``days_overdue`` and the eventual payment date are labels here, never features.
"""

from datetime import date

from cashflow_risk.domain import Invoice, InvoiceStatus
from cashflow_risk.risk.label import late_label


def _inv(*, due: date, paid: date | None) -> Invoice:
    status = InvoiceStatus.PAID if paid is not None else InvoiceStatus.OPEN
    return Invoice(
        id="I",
        business_id="B",
        customer_id="C",
        amount=1000,
        issue_date=date(2026, 1, 1),
        due_date=due,
        paid_date=paid,
        status=status,
    )


HORIZON = date(2026, 6, 30)


def test_paid_on_or_before_due_is_not_late() -> None:
    assert late_label(_inv(due=date(2026, 3, 1), paid=date(2026, 2, 20)), horizon=HORIZON) is False
    # paid exactly on the due date is on time (0 > 0 is False)
    assert late_label(_inv(due=date(2026, 3, 1), paid=date(2026, 3, 1)), horizon=HORIZON) is False


def test_paid_after_due_beyond_threshold_is_late() -> None:
    inv = _inv(due=date(2026, 3, 1), paid=date(2026, 3, 20))  # 19 days late
    assert late_label(inv, horizon=HORIZON) is True  # default X=0
    assert late_label(inv, horizon=HORIZON, days_threshold=14) is True
    assert late_label(inv, horizon=HORIZON, days_threshold=30) is False  # only 19 late


def test_unpaid_at_horizon_is_positive_even_if_paid_much_later() -> None:
    # still open at horizon -> positive
    assert late_label(_inv(due=date(2026, 5, 1), paid=None), horizon=HORIZON) is True
    # paid, but only *after* the horizon -> unpaid as-of the horizon -> positive
    late = _inv(due=date(2026, 5, 1), paid=date(2026, 8, 1))
    assert late_label(late, horizon=HORIZON) is True
