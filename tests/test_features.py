"""Behaviour of the as-of feature store.

Every feature must be computed using only information observable at ``as_of`` —
no eventual payment dates, no latent generator variables (docs/adr/0002). These
tests pin that leakage-safety as a specification.
"""

from datetime import date
from decimal import Decimal

from cashflow_risk.domain import Invoice, InvoiceStatus
from cashflow_risk.features.store import build_invoice_features

AS_OF = date(2026, 3, 1)


def _inv(id: str, issue: date, due: date, *, paid: date | None, customer: str = "C1") -> Invoice:
    return Invoice(
        id=id,
        business_id="biz",
        customer_id=customer,
        amount=Decimal("1000"),
        issue_date=issue,
        due_date=due,
        paid_date=paid,
        amount_paid=Decimal("1000") if paid else Decimal("0"),
        status=InvoiceStatus.PAID if paid else InvoiceStatus.OPEN,
    )


def _by_id(features: list, invoice_id: str):
    return next(f for f in features if f.invoice_id == invoice_id)


def test_features_summarise_prior_settled_history() -> None:
    invoices = [
        # prior, settled before AS_OF: one late (10 days), one on time
        _inv("P1", date(2026, 1, 1), date(2026, 1, 31), paid=date(2026, 2, 10)),
        _inv("P2", date(2026, 1, 5), date(2026, 2, 4), paid=date(2026, 2, 1)),
        # the open invoice we want to score
        _inv("O1", date(2026, 2, 15), date(2026, 3, 17), paid=None),
    ]

    features = build_invoice_features(invoices, as_of=AS_OF)
    o1 = _by_id(features, "O1")

    assert o1.customer_prior_count == 2
    assert o1.customer_late_rate == 0.5
    assert o1.customer_avg_overdue == 5.0  # mean(10, 0)
    assert o1.days_overdue_now == 0  # AS_OF is before O1's due date
    assert o1.is_cold_start is False


def test_invoices_settled_after_as_of_do_not_leak_into_history() -> None:
    invoices = [
        # settles AFTER as_of -> its outcome is unknown at as_of, must not count
        _inv("F1", date(2026, 1, 1), date(2026, 1, 31), paid=date(2026, 4, 1), customer="C2"),
        _inv("O2", date(2026, 2, 1), date(2026, 3, 1), paid=None, customer="C2"),
    ]

    o2 = _by_id(build_invoice_features(invoices, as_of=AS_OF), "O2")

    assert o2.customer_prior_count == 0
    assert o2.is_cold_start is True
    assert o2.customer_late_rate == 0.0


def test_days_overdue_now_counts_only_elapsed_time() -> None:
    # due 2026-02-15, as_of 2026-03-01 -> 14 days overdue so far
    invoices = [_inv("O3", date(2026, 1, 1), date(2026, 2, 15), paid=None, customer="C3")]

    o3 = _by_id(build_invoice_features(invoices, as_of=AS_OF), "O3")

    assert o3.days_overdue_now == 14
