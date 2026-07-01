"""Persisted entities. Every tenant-owned row carries ``business_id``.

We store derived results, not raw uploads (data minimisation — see
``docs/security_privacy.md``). An AnalysisRun is an immutable snapshot of one
analysis, keyed to the Business that produced it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from cashflow_risk.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class BusinessRow(Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AnalysisRunRow(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    business_id: Mapped[str] = mapped_column(
        String, ForeignKey("businesses.id"), index=True, nullable=False
    )
    as_of: Mapped[date] = mapped_column(Date)
    runway_weeks: Mapped[int] = mapped_column(Integer)
    has_shortfall: Mapped[bool] = mapped_column(Boolean)
    minimum_reserve: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


class MembershipRow(Base):
    """Grants a user a role on a Business. A user's *own* business (id == user id)
    is implicitly owned and needs no row here — memberships record access granted
    to *other* users (e.g. an invited accountant)."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "business_id", name="uq_membership"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    business_id: Mapped[str] = mapped_column(
        String, ForeignKey("businesses.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
