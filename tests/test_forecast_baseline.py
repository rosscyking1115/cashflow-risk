"""Behaviour of the deterministic-ledger forecast baseline.

These tests read as a specification of what the 13-week forecast does, using the
domain language from CONTEXT.md. They use small explicit fixtures (not the random
generator) so behaviour is pinned exactly.
"""

from datetime import date
from decimal import Decimal

from cashflow_risk.domain import Bill, Invoice, InvoiceStatus, ObligationType, TaxObligation
from cashflow_risk.forecasting.baselines import forecast_cash

AS_OF = date(2026, 1, 1)


def _invoice(amount: str, issue: date, due: date, **kw) -> Invoice:
    return Invoice(
        id=kw.pop("id", "INV-1"),
        business_id="biz",
        customer_id=kw.pop("customer_id", "cust"),
        amount=Decimal(amount),
        issue_date=issue,
        due_date=due,
        **kw,
    )


def _bill(amount: str, due: date, **kw) -> Bill:
    return Bill(
        id=kw.pop("id", "BILL-1"),
        business_id="biz",
        supplier_id=kw.pop("supplier_id", "supp"),
        amount=Decimal(amount),
        issue_date=kw.pop("issue_date", AS_OF),
        due_date=due,
        **kw,
    )


def test_flat_balance_when_no_activity() -> None:
    run = forecast_cash(
        opening_balance=Decimal("5000"),
        as_of=date(2026, 1, 1),
        invoices=[],
        bills=[],
        obligations=[],
        horizon_weeks=13,
    )

    assert len(run.weeks) == 13
    assert run.weeks[0].opening_balance == 5000.0
    assert run.weeks[-1].closing_balance == 5000.0
    assert run.has_shortfall is False
    assert run.runway_weeks == 13


def test_open_invoice_adds_inflow_in_its_due_week() -> None:
    run = forecast_cash(
        opening_balance=Decimal("1000"),
        as_of=AS_OF,
        invoices=[_invoice("500", AS_OF, due=date(2026, 1, 15))],  # +14 days -> week 2
        bills=[],
        obligations=[],
    )

    assert run.weeks[2].expected_inflow == 500.0
    assert run.weeks[2].closing_balance == 1500.0
    assert run.weeks[-1].closing_balance == 1500.0


def test_bill_can_push_balance_below_reserve() -> None:
    run = forecast_cash(
        opening_balance=Decimal("1000"),
        as_of=AS_OF,
        invoices=[],
        bills=[_bill("700", due=date(2026, 1, 5))],  # week 0
        obligations=[],
        minimum_reserve=Decimal("500"),
    )

    assert run.weeks[0].closing_balance == 300.0
    assert run.has_shortfall is True
    assert run.shortfall_weeks == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    assert run.runway_weeks == 0


def test_payment_delay_shifts_inflow_to_a_later_week() -> None:
    invoice = _invoice("1000", AS_OF, due=AS_OF)  # due immediately -> week 0
    on_time = forecast_cash(
        opening_balance=0, as_of=AS_OF, invoices=[invoice], bills=[], obligations=[]
    )
    late = forecast_cash(
        opening_balance=0,
        as_of=AS_OF,
        invoices=[invoice],
        bills=[],
        obligations=[],
        payment_delay_days=21,  # -> week 3
    )

    assert on_time.weeks[0].expected_inflow == 1000.0
    assert late.weeks[0].expected_inflow == 0.0
    assert late.weeks[3].expected_inflow == 1000.0


def test_tax_obligation_is_a_dated_outflow() -> None:
    run = forecast_cash(
        opening_balance=Decimal("2000"),
        as_of=AS_OF,
        invoices=[],
        bills=[],
        obligations=[
            TaxObligation(
                id="VAT-Q1",
                business_id="biz",
                type=ObligationType.VAT,
                amount=Decimal("800"),
                due_date=date(2026, 1, 8),  # week 1
            )
        ],
    )

    assert run.weeks[1].expected_outflow == 800.0
    assert run.weeks[1].closing_balance == 1200.0


def test_settled_invoice_is_excluded() -> None:
    run = forecast_cash(
        opening_balance=Decimal("1000"),
        as_of=AS_OF,
        invoices=[
            _invoice("999", AS_OF, due=date(2026, 1, 15), status=InvoiceStatus.PAID)
        ],
        bills=[],
        obligations=[],
    )

    assert all(w.expected_inflow == 0.0 for w in run.weeks)
    assert run.weeks[-1].closing_balance == 1000.0


def test_overdue_invoice_lands_in_first_week() -> None:
    run = forecast_cash(
        opening_balance=0,
        as_of=AS_OF,
        invoices=[_invoice("300", date(2025, 11, 1), due=date(2025, 12, 1))],
        bills=[],
        obligations=[],
    )

    assert run.weeks[0].expected_inflow == 300.0


def test_headline_story_top_customer_late_payment_breaks_week_6() -> None:
    """If a top customer's two invoices are paid 21 days late, the payroll
    reserve is breached in week 6 — the canonical user story."""
    payroll = _bill("6000", due=date(2026, 2, 12))  # +42 days -> week 6
    invoices = [
        _invoice("4000", AS_OF, due=date(2026, 1, 29), id="INV-A", customer_id="top"),
        _invoice("4000", AS_OF, due=date(2026, 1, 29), id="INV-B", customer_id="top"),
    ]
    common = dict(
        opening_balance=Decimal("8000"),
        as_of=AS_OF,
        invoices=invoices,
        bills=[payroll],
        obligations=[],
        minimum_reserve=Decimal("5000"),
    )

    on_time = forecast_cash(**common, payment_delay_days=0)
    late = forecast_cash(**common, payment_delay_days=21)

    assert on_time.has_shortfall is False
    assert late.has_shortfall is True
    assert 6 in late.shortfall_weeks
    assert late.runway_weeks == 6
    assert late.weeks[7].closing_balance == 10000.0  # recovers once invoices land
