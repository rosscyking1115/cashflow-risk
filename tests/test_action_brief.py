"""Behaviour of the deterministic action brief.

The action brief is the product surface: it turns a forecast and ranked risks
into plain English — what the risk is, why, and what to do this week. It is
decision support, never advice (docs/security_privacy.md), and every brief
carries the disclaimer and avoids forbidden wording.
"""

from datetime import date

from cashflow_risk.forecasting.baselines import forecast_cash
from cashflow_risk.reporting.action_brief import build_action_brief
from cashflow_risk.risk.baseline import RiskScore

AS_OF = date(2026, 1, 1)


def _healthy_forecast():
    return forecast_cash(
        opening_balance=10000,
        as_of=AS_OF,
        invoices=[],
        bills=[],
        obligations=[],
        minimum_reserve=2000,
    )


def test_healthy_brief_reports_no_shortfall_and_carries_disclaimer() -> None:
    brief = build_action_brief(_healthy_forecast(), [])

    assert brief.has_shortfall is False
    assert brief.runway_weeks == 13
    disclaimer = brief.disclaimer.lower()
    assert "not" in disclaimer and "advice" in disclaimer


def _shortfall_forecast():
    return forecast_cash(
        opening_balance=3000,
        as_of=AS_OF,
        invoices=[],
        bills=[],
        obligations=[],
        minimum_reserve=5000,
    )


def _score(invoice_id: str, cash_at_risk: float, probability: float = 0.7) -> RiskScore:
    return RiskScore(
        invoice_id=invoice_id,
        customer_id="C",
        probability=probability,
        band="high",
        cash_at_risk=cash_at_risk,
        drivers=["Customer has paid late 80% of the time (5 prior invoices)"],
    )


def test_shortfall_brief_names_the_week_and_invoices_to_chase() -> None:
    scores = [_score("INV-1042", 4000.0), _score("INV-1048", 2500.0)]

    brief = build_action_brief(_shortfall_forecast(), scores)

    assert brief.has_shortfall is True
    assert brief.first_shortfall_week == 1
    assert "week 1" in brief.headline
    assert "£2,000" in brief.headline  # the gap below the £5,000 reserve
    actions = " ".join(brief.recommended_actions)
    assert "INV-1042" in actions and "INV-1048" in actions


def test_risk_signals_come_from_the_top_ranked_scores() -> None:
    scores = [_score("INV-1042", 4000.0), _score("INV-1048", 2500.0), _score("INV-9", 10.0)]

    brief = build_action_brief(_shortfall_forecast(), scores, top_n=2)

    assert len(brief.risk_signals) == 2
    assert "INV-1042" in brief.risk_signals[0]
    assert "£4,000 at risk" in brief.risk_signals[0]


def test_brief_never_emits_forbidden_advice_wording() -> None:
    brief = build_action_brief(_shortfall_forecast(), [_score("INV-1042", 4000.0)])

    text = brief.text.lower()
    for forbidden in ("you should borrow", "unsafe", "tax advice", "approved credit"):
        assert forbidden not in text
