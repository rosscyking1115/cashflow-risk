"""Run the engine end to end on a synthetic UK SME and print the action brief.

    uv run python scripts/demo.py

Generates a synthetic business, scores its open invoices for late-payment risk,
forecasts 13 weeks of cash, and prints the plain-English brief — the wedge in
action. Synthetic data is for demonstration only (docs/adr/0002).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal

from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.domain import Invoice, InvoiceStatus
from cashflow_risk.features.store import build_invoice_features
from cashflow_risk.forecasting.baselines import forecast_cash
from cashflow_risk.reporting.action_brief import build_action_brief
from cashflow_risk.risk.baseline import rank_by_cash_at_risk
from cashflow_risk.risk.forecast_delay import risk_adjusted_delay_fn


def _open_at(inv: Invoice, as_of: date) -> bool:
    return inv.issue_date <= as_of and (inv.paid_date is None or inv.paid_date > as_of)


def main() -> None:
    # Windows consoles default to cp1252; the brief uses £, •, → etc.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ds = generate_dataset(GeneratorConfig(seed=1, n_customers=25))
    as_of = date(2025, 1, 1) + timedelta(weeks=30)

    features = build_invoice_features(ds.invoices, as_of=as_of)
    ranked = rank_by_cash_at_risk(features)

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
    # the forecast is timed by the same risk view that drives the ranking
    forecast = forecast_cash(
        opening_balance=8000,
        as_of=as_of,
        invoices=open_snapshot,
        bills=[],
        obligations=[],
        minimum_reserve=6000,
        payment_delay_days=risk_adjusted_delay_fn(features),
    )
    brief = build_action_brief(forecast, ranked)

    print(f"\n{ds.business.name}  —  as of {as_of:%d %b %Y}")
    print(
        f"{len(ds.customers)} customers · {len(open_snapshot)} open invoices · "
        f"runway {brief.runway_weeks}/13 weeks\n"
    )
    print("ACTION BRIEF")
    print("-" * 60)
    print(brief.headline)
    if brief.risk_signals:
        print("\nTop cash-at-risk invoices:")
        for line in brief.risk_signals:
            print(f"  • {line}")
    if brief.recommended_actions:
        print("\nWhat to do this week:")
        for line in brief.recommended_actions:
            print(f"  → {line}")
    print(f"\n{brief.disclaimer}\n")


if __name__ == "__main__":
    main()
