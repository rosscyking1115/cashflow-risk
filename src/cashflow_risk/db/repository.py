"""Tenant-scoped data access. Every query is filtered by ``business_id``.

This is where tenant isolation is enforced: :func:`get_run` matches on *both* the
run id and the owning ``business_id``, so one tenant can never read another's run
even with a guessed id. Kept free of API/DTO types so the data layer stays
independent of the transport layer.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, or_, select
from sqlalchemy.orm import Session

from cashflow_risk.db.models import (
    AnalysisRunRow,
    AuditEventRow,
    BusinessRow,
    CompanySignalRow,
    InvitationRow,
    MembershipRow,
)
from cashflow_risk.enrichment.companies_house import CompanySignals


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


def get_company_signals(session: Session, company_number: str) -> CompanySignals | None:
    row = session.get(CompanySignalRow, company_number)
    if row is None:
        return None
    return CompanySignals(
        company_number=row.company_number,
        status=row.status,
        accounts_overdue=row.accounts_overdue,
        accounts_next_due=row.accounts_next_due,
        confirmation_overdue=row.confirmation_overdue,
        has_insolvency=row.has_insolvency,
        has_charges=row.has_charges,
    )


def all_company_numbers(session: Session) -> list[str]:
    """Every cached company number — the work-list for the daily refresh worker.

    Not tenant-scoped: ``company_signals`` is shared across tenants (the same
    company can be a customer of many businesses), so the refresh is global.
    """
    return list(session.scalars(select(CompanySignalRow.company_number)))


def upsert_company_signals(session: Session, signals: CompanySignals) -> None:
    row = session.get(CompanySignalRow, signals.company_number)
    if row is None:
        row = CompanySignalRow(company_number=signals.company_number)
        session.add(row)
    row.status = signals.status
    row.accounts_overdue = signals.accounts_overdue
    row.accounts_next_due = signals.accounts_next_due
    row.confirmation_overdue = signals.confirmation_overdue
    row.has_insolvency = signals.has_insolvency
    row.has_charges = signals.has_charges
    row.refreshed_at = datetime.now(UTC)
    session.commit()


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


def purge_expired(session: Session, *, cutoff: datetime) -> tuple[int, int]:
    """Delete analysis runs and audit events created before ``cutoff``.

    The retention purge (privacy notice: results are auto-deleted after the
    retention period). Purges *results*, never accounts — business rows,
    memberships, and invitations stay. Returns (runs, events) deleted.
    """
    # session.execute() is typed as Result, but DELETE returns a CursorResult
    # (which carries rowcount) — narrow for mypy.
    runs = cast(
        "CursorResult[Any]",
        session.execute(delete(AnalysisRunRow).where(AnalysisRunRow.created_at < cutoff)),
    ).rowcount
    events = cast(
        "CursorResult[Any]",
        session.execute(delete(AuditEventRow).where(AuditEventRow.created_at < cutoff)),
    ).rowcount
    session.commit()
    return runs, events


def record_audit_event(
    session: Session,
    *,
    business_id: str,
    actor_user_id: str,
    action: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """Append one audit event. ``detail`` must hold ids/counts only — never
    amounts, customer names, or emails (see AuditEventRow)."""
    ensure_business(session, business_id)
    session.flush()  # Business row before the event (FK on Postgres)
    session.add(
        AuditEventRow(
            business_id=business_id, actor_user_id=actor_user_id, action=action, detail=detail
        )
    )
    session.commit()


def list_audit_events(session: Session, *, business_id: str) -> list[AuditEventRow]:
    stmt = (
        select(AuditEventRow)
        .where(AuditEventRow.business_id == business_id)
        .order_by(AuditEventRow.created_at, AuditEventRow.id)
    )
    return list(session.scalars(stmt))


def export_account(session: Session, *, user_id: str, email: str | None) -> dict[str, Any]:
    """Everything held for a user — the data-portability / SAR artifact (DPIA R6).

    Covers their own business (id == user_id): profile, every run with its full
    payload, memberships they hold elsewhere, members they have granted access
    to, and invitations they have sent.
    """
    business = get_business(session, user_id)
    members = list(
        session.scalars(select(MembershipRow).where(MembershipRow.business_id == user_id))
    )
    return {
        "exported_for": {"user_id": user_id, "email": email},
        "exported_at": datetime.now(UTC).isoformat(),
        "business": {
            "id": user_id,
            "name": business.name if business else None,
            "created_at": business.created_at.isoformat() if business else None,
        },
        "runs": [
            {
                "id": r.id,
                "as_of": r.as_of.isoformat(),
                "runway_weeks": r.runway_weeks,
                "has_shortfall": r.has_shortfall,
                "minimum_reserve": r.minimum_reserve,
                "created_at": r.created_at.isoformat(),
                "payload": r.payload,
            }
            for r in list_runs(session, business_id=user_id)
        ],
        "memberships": [
            {"business_id": m.business_id, "role": m.role, "created_at": m.created_at.isoformat()}
            for m in list_memberships(session, user_id=user_id)
        ],
        "members": [
            {"user_id": m.user_id, "role": m.role, "created_at": m.created_at.isoformat()}
            for m in members
        ],
        "invitations_sent": [
            {"email": i.email, "role": i.role, "created_at": i.created_at.isoformat()}
            for i in list_invitations(session, business_id=user_id)
        ],
    }


def delete_account(session: Session, *, user_id: str, email: str | None) -> None:
    """Erase everything held for a user (DPIA R6: right to erasure). Idempotent.

    Deletes their business's runs, memberships in both directions (access they
    granted and access they hold), invitations they sent, invitations addressed
    to their email, and finally the business row. Never touches other tenants;
    ``company_signals`` stays (public-register data, shared, not personal)."""
    session.execute(delete(AnalysisRunRow).where(AnalysisRunRow.business_id == user_id))
    session.execute(delete(AuditEventRow).where(AuditEventRow.business_id == user_id))
    session.execute(
        delete(MembershipRow).where(
            or_(MembershipRow.business_id == user_id, MembershipRow.user_id == user_id)
        )
    )
    invitation_filter = InvitationRow.business_id == user_id
    if email:
        invitation_filter = or_(invitation_filter, InvitationRow.email == email.lower())
    session.execute(delete(InvitationRow).where(invitation_filter))
    business = session.get(BusinessRow, user_id)
    if business is not None:
        session.delete(business)
    session.commit()


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
