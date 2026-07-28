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


class CompanySignalRow(Base):
    """Cached Companies House signals for a company number. Shared across tenants
    (the same company can be a customer of many businesses) — not tenant-private."""

    __tablename__ = "company_signals"

    company_number: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str | None] = mapped_column(String, default=None)
    accounts_overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    accounts_next_due: Mapped[date | None] = mapped_column(Date, default=None)
    confirmation_overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    has_insolvency: Mapped[bool] = mapped_column(Boolean, default=False)
    has_charges: Mapped[bool] = mapped_column(Boolean, default=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditEventRow(Base):
    """One recorded action on a Business — the append-only audit log.

    Append-only; tenant-scoped like everything else. ``detail`` holds ids and
    counts only — never amounts, customer names, or emails (the trail must be
    safe to show and safe to keep). Erased with the account (right to erasure
    beats audit retention for a tenant's own trail)."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    business_id: Mapped[str] = mapped_column(
        String, ForeignKey("businesses.id"), index=True, nullable=False
    )
    actor_user_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


class InvitationRow(Base):
    """A pending grant of a role on a Business to an email address. It becomes a
    Membership when a signed-in user with that email claims it."""

    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("email", "business_id", name="uq_invitation"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, index=True)
    business_id: Mapped[str] = mapped_column(
        String, ForeignKey("businesses.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
