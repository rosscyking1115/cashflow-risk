"""JSON DTOs for the API, plus mappers from the engine's internal types.

The engine works in Decimal and frozen dataclasses; the wire format is plain
JSON-friendly types. Keeping the mapping here means the dashboard depends on a
stable shape, not on internal representations.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from cashflow_risk.analysis import Analysis
from cashflow_risk.forecasting.baselines import WeekForecast
from cashflow_risk.reporting.action_brief import ActionBrief
from cashflow_risk.risk.baseline import RiskScore


class WeekDTO(BaseModel):
    index: int
    week_start: date
    opening_balance: float
    expected_inflow: float
    expected_outflow: float
    closing_balance: float

    @classmethod
    def of(cls, w: WeekForecast) -> WeekDTO:
        return cls(
            index=w.index,
            week_start=w.week_start,
            opening_balance=round(w.opening_balance, 2),
            expected_inflow=round(w.expected_inflow, 2),
            expected_outflow=round(w.expected_outflow, 2),
            closing_balance=round(w.closing_balance, 2),
        )


class RiskDTO(BaseModel):
    invoice_id: str
    customer_id: str
    probability: float
    band: str
    cash_at_risk: float
    drivers: list[str]

    @classmethod
    def of(cls, s: RiskScore) -> RiskDTO:
        return cls(
            invoice_id=s.invoice_id,
            customer_id=s.customer_id,
            probability=round(s.probability, 4),
            band=s.band,
            cash_at_risk=round(s.cash_at_risk, 2),
            drivers=s.drivers,
        )


class BriefDTO(BaseModel):
    headline: str
    runway_weeks: int
    has_shortfall: bool
    first_shortfall_week: int | None
    risk_signals: list[str]
    recommended_actions: list[str]
    disclaimer: str

    @classmethod
    def of(cls, b: ActionBrief) -> BriefDTO:
        return cls(
            headline=b.headline,
            runway_weeks=b.runway_weeks,
            has_shortfall=b.has_shortfall,
            first_shortfall_week=b.first_shortfall_week,
            risk_signals=b.risk_signals,
            recommended_actions=b.recommended_actions,
            disclaimer=b.disclaimer,
        )


class IssueDTO(BaseModel):
    row: int
    message: str
    field: str | None
    severity: str


class RunSummary(BaseModel):
    """A row in a Business's analysis history."""

    id: str
    as_of: date
    runway_weeks: int
    has_shortfall: bool
    created_at: datetime


class AnalysisResponse(BaseModel):
    business_id: str
    as_of: date
    minimum_reserve: float
    weeks: list[WeekDTO]
    top_risks: list[RiskDTO]
    brief: BriefDTO
    data_issues: list[IssueDTO] = []
    run_id: str | None = None  # set when the analysis is persisted

    @classmethod
    def of(
        cls,
        analysis: Analysis,
        *,
        top_n: int = 10,
        data_issues: list[IssueDTO] | None = None,
    ) -> AnalysisResponse:
        return cls(
            business_id=analysis.business_id,
            as_of=analysis.as_of,
            minimum_reserve=round(analysis.forecast.minimum_reserve, 2),
            weeks=[WeekDTO.of(w) for w in analysis.forecast.weeks],
            top_risks=[RiskDTO.of(s) for s in analysis.ranked_risk[:top_n]],
            brief=BriefDTO.of(analysis.brief),
            data_issues=data_issues or [],
        )
