"""End-to-end: synthetic data → features → ranked risk → forecast → action brief.

Guards that the engine's pieces compose into a coherent brief, and documents the
intended flow. Uses an as-of snapshot of invoices open at the reference date.
"""

from datetime import date, timedelta
from decimal import Decimal

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.domain import Invoice, InvoiceStatus
from cashflow_risk.features.store import build_invoice_features
from cashflow_risk.forecasting.baselines import forecast_cash
from cashflow_risk.reporting.action_brief import build_action_brief
from cashflow_risk.risk.baseline import rank_by_cash_at_risk


def _open_at(inv: Invoice, as_of: date) -> bool:
    return inv.issue_date <= as_of and (inv.paid_date is None or inv.paid_date > as_of)


def test_pipeline_produces_a_coherent_brief_on_synthetic_data() -> None:
    ds = generate_dataset(GeneratorConfig(seed=1, n_customers=25))
    as_of = date(2025, 1, 1) + timedelta(weeks=30)

    features = build_invoice_features(ds.invoices, as_of=as_of)
    assert features  # mid-year there are open invoices to score

    ranked = rank_by_cash_at_risk(features)
    assert ranked[0].cash_at_risk >= ranked[-1].cash_at_risk  # sorted, highest first
    assert all(0.0 <= s.probability <= 1.0 for s in ranked)

    # an as-of snapshot: invoices unpaid at the reference date are genuinely open
    open_snapshot = [
        inv.model_copy(
            update={
                "status": InvoiceStatus.OPEN,
                "paid_date": None,
                "amount_paid": Decimal("0"),
            }
        )
        for inv in ds.invoices
        if _open_at(inv, as_of)
    ]

    forecast = forecast_cash(
        opening_balance=5000,
        as_of=as_of,
        invoices=open_snapshot,
        bills=[],
        obligations=[],
        minimum_reserve=2000,
    )
    brief = build_action_brief(forecast, ranked)

    assert 0 <= brief.runway_weeks <= 13
    assert brief.risk_signals  # the ranked risks surfaced
    assert brief.text.strip()
    assert "advice" in brief.disclaimer.lower()
