"""Behaviour of the analysis orchestration.

`analyze_invoices` is the single entry point that turns a Business's invoices
into the full picture — ranked risk, a risk-timed forecast, and an action brief —
so the API and the demo share exactly one code path.
"""

from datetime import date
from decimal import Decimal

from cashflow_risk.analysis import analyze_invoices
from cashflow_risk.domain import Invoice, InvoiceStatus

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


def test_analyze_returns_forecast_ranked_risk_and_brief() -> None:
    invoices = [
        _inv("P1", date(2026, 1, 1), date(2026, 1, 31), paid=date(2026, 2, 14)),  # prior, late
        _inv("O1", date(2026, 2, 15), date(2026, 3, 31), paid=None),  # open
    ]

    analysis = analyze_invoices(
        invoices,
        as_of=AS_OF,
        opening_balance=Decimal("5000"),
        minimum_reserve=Decimal("2000"),
        business_id="biz",
    )

    assert analysis.as_of == AS_OF
    assert analysis.forecast.horizon_weeks == 13
    assert any(s.invoice_id == "O1" for s in analysis.ranked_risk)
    assert analysis.brief.text.strip()
