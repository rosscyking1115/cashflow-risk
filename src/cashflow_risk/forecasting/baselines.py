"""Deterministic-ledger cash forecast — the baseline to beat.

Most of an SME's near-term cash position is *known*: invoices with due dates,
bills, and scheduled tax obligations. This baseline projects those known, dated
obligations into 13 weekly buckets, applying an assumed payment delay to
receivables. This, not seasonal-naive, is the
real baseline any ML forecast must beat.

It is intentionally simple and deterministic. Probabilistic intervals and
risk-driven per-invoice delays are layered on in later phases.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from cashflow_risk.domain import Bill, Invoice, TaxObligation

Number = Decimal | float | int
DelaySpec = int | Callable[[Invoice], int]


@dataclass(frozen=True)
class WeekForecast:
    """One week of the projection (a bucket of a Forecast run)."""

    index: int
    week_start: date
    opening_balance: float
    expected_inflow: float
    expected_outflow: float

    @property
    def week_end(self) -> date:
        return self.week_start + timedelta(days=7)

    @property
    def net(self) -> float:
        return self.expected_inflow - self.expected_outflow

    @property
    def closing_balance(self) -> float:
        return self.opening_balance + self.net


@dataclass(frozen=True)
class ForecastRun:
    """A 13-week weekly cash projection for a Business at a point in time."""

    as_of: date
    horizon_weeks: int
    minimum_reserve: float
    weeks: list[WeekForecast]

    @property
    def shortfall_weeks(self) -> list[int]:
        """Indices of weeks whose closing balance falls below the reserve."""
        return [w.index for w in self.weeks if w.closing_balance < self.minimum_reserve]

    @property
    def has_shortfall(self) -> bool:
        return bool(self.shortfall_weeks)

    @property
    def runway_weeks(self) -> int:
        """Whole weeks until the first Shortfall; ``horizon_weeks`` if none."""
        for w in self.weeks:
            if w.closing_balance < self.minimum_reserve:
                return w.index
        return self.horizon_weeks


def _delay_for(invoice: Invoice, delay: DelaySpec) -> int:
    return delay(invoice) if callable(delay) else delay


def forecast_cash(
    *,
    opening_balance: Number,
    as_of: date,
    invoices: Sequence[Invoice],
    bills: Sequence[Bill],
    obligations: Sequence[TaxObligation],
    horizon_weeks: int = 13,
    minimum_reserve: Number = 0.0,
    payment_delay_days: DelaySpec = 0,
) -> ForecastRun:
    """Project cash over ``horizon_weeks`` weekly buckets from ``as_of``.

    Only *open* invoices and bills are projected (settled items are assumed
    already reflected in ``opening_balance``). Receivables land in the week of
    ``due_date + payment_delay_days`` — pass a callable to vary the delay per
    invoice (this is the "what-if a customer pays late" scenario toggle).
    Anything dated before ``as_of`` lands in week 0; anything beyond the horizon
    is ignored.
    """
    if horizon_weeks < 1:
        raise ValueError("horizon_weeks must be >= 1")

    inflow = [0.0] * horizon_weeks
    outflow = [0.0] * horizon_weeks

    def bucket(d: date) -> int | None:
        if d < as_of:
            return 0
        idx = (d - as_of).days // 7
        return idx if idx < horizon_weeks else None

    for inv in invoices:
        if inv.is_settled:
            continue
        when = inv.due_date + timedelta(days=_delay_for(inv, payment_delay_days))
        i = bucket(when)
        if i is not None:
            inflow[i] += float(inv.outstanding)

    for bill in bills:
        if bill.is_settled:
            continue
        i = bucket(bill.due_date)
        if i is not None:
            outflow[i] += float(bill.amount)

    for ob in obligations:
        i = bucket(ob.due_date)
        if i is not None:
            outflow[i] += float(ob.amount)

    weeks: list[WeekForecast] = []
    opening = float(opening_balance)
    for i in range(horizon_weeks):
        wk = WeekForecast(
            index=i,
            week_start=as_of + timedelta(days=7 * i),
            opening_balance=opening,
            expected_inflow=inflow[i],
            expected_outflow=outflow[i],
        )
        weeks.append(wk)
        opening = wk.closing_balance

    return ForecastRun(
        as_of=as_of,
        horizon_weeks=horizon_weeks,
        minimum_reserve=float(minimum_reserve),
        weeks=weeks,
    )
