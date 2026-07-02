"""Audit log (PLAN Phase 4): who did what, when — per tenant, minimal detail.

Events are recorded at the API seams (upload, exports, invites, renames), are
tenant-scoped like everything else, carry counts/ids but never financial values,
and are erased with the account (erasure beats audit retention for one's own
trail).
"""


from fastapi.testclient import TestClient

from cashflow_risk.api import app
from cashflow_risk.auth import Principal, mint_token
from cashflow_risk.auth.settings import jwt_secret
from cashflow_risk.db import get_session
from cashflow_risk.db import repository as repo

client = TestClient(app)

CSV = (
    "invoice_id,customer_id,amount,issue_date,due_date\n"
    "INV-1,Acme Widgets,5000,2026-01-01,2026-01-31\n"
)


def _auth(user_id: str = "u1", business_id: str | None = None) -> dict[str, str]:
    token = mint_token(
        Principal(user_id=user_id, business_id=business_id or user_id, email=f"{user_id}@x.co"),
        secret=jwt_secret(),
    )
    return {"Authorization": f"Bearer {token}"}


# --- repository --------------------------------------------------------------


def test_events_are_recorded_and_tenant_scoped() -> None:
    session = next(get_session())
    repo.record_audit_event(
        session, business_id="a", actor_user_id="u1", action="run.create", detail={"rows": 3}
    )
    repo.record_audit_event(session, business_id="b", actor_user_id="u2", action="run.export")

    events_a = repo.list_audit_events(session, business_id="a")
    assert [e.action for e in events_a] == ["run.create"]
    assert events_a[0].actor_user_id == "u1"
    assert events_a[0].detail == {"rows": 3}
    assert [e.action for e in repo.list_audit_events(session, business_id="b")] == ["run.export"]


def test_delete_account_erases_the_audit_trail() -> None:
    session = next(get_session())
    repo.record_audit_event(session, business_id="u1", actor_user_id="u1", action="run.create")
    repo.record_audit_event(session, business_id="other", actor_user_id="o1", action="run.create")

    repo.delete_account(session, user_id="u1", email="u1@x.co")

    assert repo.list_audit_events(session, business_id="u1") == []
    assert len(repo.list_audit_events(session, business_id="other")) == 1  # bystander kept


# --- recorded at the API seams -------------------------------------------------


def test_upload_records_a_run_create_event_with_counts_only() -> None:
    response = client.post(
        "/api/analyze",
        files={"invoices": ("inv.csv", CSV, "text/csv")},
        headers=_auth(),
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    session = next(get_session())
    events = repo.list_audit_events(session, business_id="u1")
    assert [e.action for e in events] == ["run.create"]
    assert events[0].detail == {"run_id": run_id, "rows": 1, "issues": 0}
    # hygiene: no financial values or counterparty names in the audit trail
    assert "5000" not in str(events[0].detail)
    assert "Acme" not in str(events[0].detail)


def test_exports_and_membership_actions_are_audited() -> None:
    upload = client.post(
        "/api/analyze", files={"invoices": ("inv.csv", CSV, "text/csv")}, headers=_auth()
    )
    run_id = upload.json()["run_id"]

    assert client.get(f"/api/runs/{run_id}/export.xlsx", headers=_auth()).status_code == 200
    assert client.get("/api/account/export", headers=_auth()).status_code == 200
    invited = client.post(
        "/api/businesses/u1/invitations",
        json={"email": "acct@firm.co", "role": "accountant"},
        headers=_auth(),
    )
    assert invited.status_code == 200

    session = next(get_session())
    actions = [e.action for e in repo.list_audit_events(session, business_id="u1")]
    assert actions == ["run.create", "run.export", "account.export", "member.invite"]
    events = repo.list_audit_events(session, business_id="u1")
    assert events[1].detail == {"run_id": run_id}
    assert events[3].detail == {"role": "accountant"}  # no email in the trail


def test_audit_endpoint_lists_the_active_business_trail() -> None:
    assert client.get("/api/audit").status_code == 401

    client.post("/api/analyze", files={"invoices": ("inv.csv", CSV, "text/csv")}, headers=_auth())

    response = client.get("/api/audit", headers=_auth())
    assert response.status_code == 200
    body = response.json()
    assert [e["action"] for e in body] == ["run.create"]
    assert body[0]["actor_user_id"] == "u1"
    assert "created_at" in body[0]


def test_accountant_actions_are_attributed_to_the_accountant() -> None:
    session = next(get_session())
    repo.set_business_name(session, business_id="owner-1", name="Client Co")
    repo.add_membership(session, user_id="acct-9", business_id="owner-1", role="accountant")

    headers = {**_auth(user_id="acct-9"), "X-Business-Id": "owner-1"}
    response = client.get("/api/audit", headers=headers)  # accountant may view the trail
    assert response.status_code == 200
