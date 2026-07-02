"""Retention auto-purge (privacy notice: results older than 24 months are
deleted automatically). Purges analysis runs and audit events past the cutoff;
newer data and other tables are untouched."""

from datetime import UTC, date, datetime, timedelta

from cashflow_risk.db import get_session
from cashflow_risk.db import repository as repo
from cashflow_risk.db.models import AnalysisRunRow, AuditEventRow


def _save_run(session, run_id: str, *, business_id: str = "u1") -> None:
    repo.save_run(
        session,
        run_id=run_id,
        business_id=business_id,
        as_of=date(2026, 1, 1),
        runway_weeks=9,
        has_shortfall=False,
        minimum_reserve=0.0,
        payload={},
    )


def _age(session, model: type, row_id: str, *, days: int) -> None:
    row = session.get(model, row_id)
    row.created_at = datetime.now(UTC) - timedelta(days=days)
    session.commit()


def test_purge_removes_only_expired_runs_and_events() -> None:
    session = next(get_session())
    _save_run(session, "old-run")
    _save_run(session, "new-run")
    _age(session, AnalysisRunRow, "old-run", days=800)
    repo.record_audit_event(session, business_id="u1", actor_user_id="u1", action="run.create")
    old_event = repo.list_audit_events(session, business_id="u1")[0]
    _age(session, AuditEventRow, old_event.id, days=800)
    repo.record_audit_event(session, business_id="u1", actor_user_id="u1", action="run.export")

    cutoff = datetime.now(UTC) - timedelta(days=730)
    runs_purged, events_purged = repo.purge_expired(session, cutoff=cutoff)

    assert (runs_purged, events_purged) == (1, 1)
    assert [r.id for r in repo.list_runs(session, business_id="u1")] == ["new-run"]
    assert [e.action for e in repo.list_audit_events(session, business_id="u1")] == ["run.export"]
    # the business row itself survives — retention purges results, not accounts
    assert repo.get_business(session, "u1") is not None


def test_purge_with_nothing_expired_is_a_noop() -> None:
    session = next(get_session())
    _save_run(session, "fresh")

    cutoff = datetime.now(UTC) - timedelta(days=730)
    assert repo.purge_expired(session, cutoff=cutoff) == (0, 0)
    assert len(repo.list_runs(session, business_id="u1")) == 1
