"""Behaviour of the rules-based late-payment risk baseline.

A transparent baseline — rules before ML. Every score is a bounded
probability with a plain-English "why", and ranking is by *expected cash at
risk* — outstanding amount weighted by late probability — not probability alone.
"""

from datetime import date

import pytest

from cashflow_risk.enrichment.companies_house import CompanySignals
from cashflow_risk.features.store import InvoiceFeatures
from cashflow_risk.risk.baseline import rank_by_cash_at_risk, score_late_probability


def _feat(**kw: object) -> InvoiceFeatures:
    defaults: dict[str, object] = dict(
        invoice_id="I",
        customer_id="C",
        as_of=date(2026, 3, 1),
        amount=1000.0,
        terms_days=30,
        days_overdue_now=0,
        customer_prior_count=4,
        customer_late_rate=0.0,
        customer_avg_overdue=0.0,
        is_cold_start=False,
    )
    defaults.update(kw)
    return InvoiceFeatures(**defaults)  # type: ignore[arg-type]


def test_score_is_a_bounded_probability_with_cash_at_risk_and_a_reason() -> None:
    score = score_late_probability(_feat(amount=1000.0))

    assert 0.0 <= score.probability <= 1.0
    assert score.cash_at_risk == pytest.approx(1000.0 * score.probability)
    assert score.drivers  # always explainable


def test_higher_customer_late_rate_raises_probability() -> None:
    low = score_late_probability(_feat(customer_late_rate=0.1))
    high = score_late_probability(_feat(customer_late_rate=0.9))

    assert high.probability > low.probability


def test_already_overdue_invoice_scores_higher() -> None:
    fresh = score_late_probability(_feat(days_overdue_now=0))
    overdue = score_late_probability(_feat(days_overdue_now=45))

    assert overdue.probability > fresh.probability
    assert "overdue" in " ".join(overdue.drivers).lower()


def test_cold_start_is_flagged_and_nudges_risk_up() -> None:
    known = score_late_probability(_feat(is_cold_start=False, customer_prior_count=4))
    cold = score_late_probability(
        _feat(is_cold_start=True, customer_prior_count=0, customer_late_rate=0.0)
    )

    assert cold.probability > known.probability
    assert any("history" in d.lower() for d in cold.drivers)


def test_chronic_late_payer_lands_in_a_high_band_with_a_reason() -> None:
    score = score_late_probability(_feat(customer_late_rate=0.85, customer_prior_count=6))

    assert score.band in ("medium", "high")
    assert any("paid late" in d for d in score.drivers)


def test_companies_house_signals_raise_the_score_and_add_a_driver() -> None:
    base = score_late_probability(_feat(customer_late_rate=0.2))
    insolvent = CompanySignals(
        company_number="12345678",
        status="active",
        accounts_overdue=True,
        accounts_next_due=None,
        confirmation_overdue=False,
        has_insolvency=True,
        has_charges=False,
    )
    enriched = score_late_probability(_feat(customer_late_rate=0.2), insolvent)

    assert enriched.probability > base.probability
    assert any("insolvency" in d.lower() for d in enriched.drivers)


def test_ranking_applies_signals_by_company_number() -> None:
    clean = _feat(invoice_id="A", customer_late_rate=0.2, company_number="00000001")
    flagged = _feat(invoice_id="B", customer_late_rate=0.2, company_number="00000002")
    signals = {"00000002": CompanySignals("00000002", "active", True, None, True, True, True)}

    ranked = {s.invoice_id: s for s in rank_by_cash_at_risk([clean, flagged], signals)}

    assert ranked["B"].probability > ranked["A"].probability


def test_ranking_is_by_expected_exposure_not_probability_alone() -> None:
    small_risky = _feat(invoice_id="SMALL", amount=1000.0, customer_late_rate=0.9)
    big_safer = _feat(invoice_id="BIG", amount=10000.0, customer_late_rate=0.1)

    ranked = rank_by_cash_at_risk([small_risky, big_safer])

    # the big, lower-probability invoice carries more cash at risk
    assert ranked[0].invoice_id == "BIG"
    assert ranked[0].cash_at_risk > ranked[1].cash_at_risk
