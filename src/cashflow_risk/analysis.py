"""Analysis orchestration — the engine's single entry point.

Turns a Business's invoices (plus optional bills and tax obligations) into the
whole picture: cash-at-risk-ranked invoices, a forecast whose timing is driven by
the same risk view, and a plain-English action brief. The API and the demo both
call this, so there is exactly one path from data to decision.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cashflow_risk.domain import Bill, Invoice, InvoiceStatus, TaxObligation
from cashflow_risk.enrichment.companies_house import CompanySignals
from cashflow_risk.features.store import build_invoice_features, is_open_at
from cashflow_risk.forecasting.baselines import ForecastRun, forecast_cash
from cashflow_risk.reporting.action_brief import ActionBrief, build_action_brief
from cashflow_risk.risk.baseline import RiskScore, rank_by_cash_at_risk
from cashflow_risk.risk.forecast_delay import risk_adjusted_delay_fn


@dataclass(frozen=True)
class Analysis:
    """Everything the dashboard needs for one Business at one point in time."""

    business_id: str
    as_of: date
    forecast: ForecastRun
    ranked_risk: list[RiskScore]
    brief: ActionBrief


def _open_snapshot(invoices: Sequence[Invoice], as_of: date) -> list[Invoice]:
    """Invoices unpaid at ``as_of``, presented as genuinely open for forecasting."""
    return [
        inv.model_copy(
            update={
                "status": InvoiceStatus.OPEN,
                "paid_date": None,
                "amount_paid": Decimal("0"),
            }
        )
        for inv in invoices
        if is_open_at(inv, as_of)
    ]


def analyze_invoices(
    invoices: Sequence[Invoice],
    *,
    as_of: date,
    opening_balance: Decimal | float,
    minimum_reserve: Decimal | float,
    business_id: str,
    bills: Sequence[Bill] = (),
    obligations: Sequence[TaxObligation] = (),
    horizon_weeks: int = 13,
    company_signals: dict[str, CompanySignals] | None = None,
) -> Analysis:
    features = build_invoice_features(invoices, as_of=as_of)
    ranked = rank_by_cash_at_risk(features, company_signals)

    forecast = forecast_cash(
        opening_balance=opening_balance,
        as_of=as_of,
        invoices=_open_snapshot(invoices, as_of),
        bills=bills,
        obligations=obligations,
        minimum_reserve=minimum_reserve,
        horizon_weeks=horizon_weeks,
        payment_delay_days=risk_adjusted_delay_fn(features),
    )
    brief = build_action_brief(forecast, ranked)

    return Analysis(
        business_id=business_id,
        as_of=as_of,
        forecast=forecast,
        ranked_risk=ranked,
        brief=brief,
    )
