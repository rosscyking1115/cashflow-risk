"""Tenant-scoped data access. Every query is filtered by ``business_id``.

This is where tenant isolation is enforced: :func:`get_run` matches on *both* the
run id and the owning ``business_id``, so one tenant can never read another's run
even with a guessed id. Kept free of API/DTO types so the data layer stays
independent of the transport layer.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cashflow_risk.db.models import (
    AnalysisRunRow,
    BusinessRow,
    InvitationRow,
    MembershipRow,
)


def ensure_business(session: Session, business_id: str, name: str | None = None) -> BusinessRow:
    business = session.get(BusinessRow, business_id)
    if business is None:
        business = BusinessRow(id=business_id, name=name)
        session.add(business)
    return business


def save_run(
    session: Session,
    *,
    run_id: str,
    business_id: str,
    as_of: date,
    runway_weeks: int,
    has_shortfall: bool,
    minimum_reserve: float,
    payload: dict[str, Any],
) -> AnalysisRunRow:
    ensure_business(session, business_id)
    session.flush()  # insert the Business before the run (satisfies the FK on Postgres)
    row = AnalysisRunRow(
        id=run_id,
        business_id=business_id,
        as_of=as_of,
        runway_weeks=runway_weeks,
        has_shortfall=has_shortfall,
        minimum_reserve=minimum_reserve,
        payload=payload,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_runs(session: Session, *, business_id: str) -> list[AnalysisRunRow]:
    stmt = (
        select(AnalysisRunRow)
        .where(AnalysisRunRow.business_id == business_id)
        .order_by(AnalysisRunRow.created_at.desc())
    )
    return list(session.scalars(stmt))


def get_run(session: Session, *, business_id: str, run_id: str) -> AnalysisRunRow | None:
    stmt = select(AnalysisRunRow).where(
        AnalysisRunRow.id == run_id,
        AnalysisRunRow.business_id == business_id,
    )
    return session.scalars(stmt).first()


def get_business(session: Session, business_id: str) -> BusinessRow | None:
    return session.get(BusinessRow, business_id)


def set_business_name(session: Session, *, business_id: str, name: str) -> BusinessRow:
    business = ensure_business(session, business_id, name)
    business.name = name
    session.commit()
    return business


def get_membership(session: Session, *, user_id: str, business_id: str) -> MembershipRow | None:
    stmt = select(MembershipRow).where(
        MembershipRow.user_id == user_id,
        MembershipRow.business_id == business_id,
    )
    return session.scalars(stmt).first()


def list_memberships(session: Session, *, user_id: str) -> list[MembershipRow]:
    stmt = (
        select(MembershipRow)
        .where(MembershipRow.user_id == user_id)
        .order_by(MembershipRow.created_at)
    )
    return list(session.scalars(stmt))


def add_membership(
    session: Session, *, user_id: str, business_id: str, role: str
) -> MembershipRow:
    ensure_business(session, business_id)
    session.flush()  # insert the Business before the membership (FK on Postgres)
    existing = get_membership(session, user_id=user_id, business_id=business_id)
    if existing is not None:
        existing.role = role
        session.commit()
        return existing
    membership = MembershipRow(user_id=user_id, business_id=business_id, role=role)
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


def create_invitation(
    session: Session, *, email: str, business_id: str, role: str
) -> InvitationRow:
    ensure_business(session, business_id)
    session.flush()  # insert the Business before the invitation (FK on Postgres)
    stmt = select(InvitationRow).where(
        InvitationRow.email == email, InvitationRow.business_id == business_id
    )
    existing = session.scalars(stmt).first()
    if existing is not None:
        existing.role = role
        session.commit()
        return existing
    invitation = InvitationRow(email=email, business_id=business_id, role=role)
    session.add(invitation)
    session.commit()
    session.refresh(invitation)
    return invitation


def list_invitations(session: Session, *, business_id: str) -> list[InvitationRow]:
    stmt = (
        select(InvitationRow)
        .where(InvitationRow.business_id == business_id)
        .order_by(InvitationRow.created_at)
    )
    return list(session.scalars(stmt))


def claim_invitations(session: Session, *, user_id: str, email: str) -> None:
    """Turn any pending invitations for ``email`` into memberships for ``user_id``."""
    invitations = list(session.scalars(select(InvitationRow).where(InvitationRow.email == email)))
    for invitation in invitations:
        add_membership(
            session, user_id=user_id, business_id=invitation.business_id, role=invitation.role
        )
        session.delete(invitation)
    if invitations:
        session.commit()
