"""Deterministic action brief — the plain-English product surface.

Combines a Forecast run and the cash-at-risk-ranked Risk scores into a short
brief: the headline risk, the drivers behind it, and the specific invoices to
chase this week. Templates are deterministic and first-party only — we never
characterise a customer, recommend borrowing, or give regulated advice (PLAN
§8.6, docs/security_privacy.md). LLM-written summaries come only once these
rules are trusted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cashflow_risk.forecasting.baselines import ForecastRun
from cashflow_risk.risk.baseline import RiskScore

DISCLAIMER = (
    "This is a cashflow risk estimate for planning support only, based on your "
    "own data. It is not accounting, tax, legal, credit, or investment advice — "
    "review with your accountant before acting."
)


@dataclass(frozen=True)
class ActionBrief:
    """The headline, explained risks, and recommended actions for a Business."""

    headline: str
    runway_weeks: int
    has_shortfall: bool
    first_shortfall_week: int | None  # 1-indexed, for humans
    risk_signals: list[str]
    recommended_actions: list[str]
    disclaimer: str = DISCLAIMER

    @property
    def text(self) -> str:
        parts = [self.headline, *self.risk_signals, *self.recommended_actions, self.disclaimer]
        return "\n".join(parts)


def _money(amount: float) -> str:
    return f"£{amount:,.0f}"


def build_action_brief(
    forecast: ForecastRun,
    ranked_scores: Sequence[RiskScore],
    *,
    top_n: int = 3,
) -> ActionBrief:
    top = list(ranked_scores)[:top_n]

    risk_signals = [
        f"{s.invoice_id}: {_money(s.cash_at_risk)} at risk "
        f"({s.probability:.0%} late) — {s.drivers[0]}"
        for s in top
    ]

    if forecast.has_shortfall:
        idx = min(forecast.shortfall_weeks)
        week = forecast.weeks[idx]
        gap = forecast.minimum_reserve - week.closing_balance
        first_week = idx + 1
        headline = (
            f"Cash is projected to fall {_money(gap)} below your "
            f"{_money(forecast.minimum_reserve)} reserve in week {first_week} "
            f"(w/c {week.week_start:%d %b %Y})."
        )
        actions: list[str] = []
        if top:
            named = ", ".join(s.invoice_id for s in top)
            actions.append(
                f"Chase {named} this week — collecting them on time is your "
                f"largest lever against the week {first_week} shortfall."
            )
        else:
            actions.append(
                f"Review upcoming outflows around week {first_week}; consider "
                "bringing forward expected receipts or deferring discretionary spend."
            )
    else:
        first_week = None
        headline = (
            f"Cash is projected to stay above your "
            f"{_money(forecast.minimum_reserve)} reserve for all "
            f"{forecast.horizon_weeks} weeks."
        )
        actions = []
        if top:
            actions.append(
                f"No shortfall expected, but {top[0].invoice_id} carries the most "
                f"cash at risk ({_money(top[0].cash_at_risk)}) — worth chasing early."
            )

    return ActionBrief(
        headline=headline,
        runway_weeks=forecast.runway_weeks,
        has_shortfall=forecast.has_shortfall,
        first_shortfall_week=first_week,
        risk_signals=risk_signals,
        recommended_actions=actions,
    )
