"""Self-serve account export + delete (DPIA R6: access/erasure rights).

Export returns everything held for the user (their business, runs incl. full
payloads, memberships, invitations) — the data-portability / SAR artifact.
Delete erases it all, and only it: other tenants' data must be untouched.
Both act on the *user* (their own business), never the switched active business.
"""

from datetime import date

from fastapi.testclient import TestClient

from cashflow_risk.api import app
from cashflow_risk.auth import Principal, mint_token
from cashflow_risk.auth.settings import jwt_secret
from cashflow_risk.db import get_session
from cashflow_risk.db import repository as repo

client = TestClient(app)


def _auth(user_id: str = "u1", email: str = "u1@example.co") -> dict[str, str]:
    token = mint_token(
        Principal(user_id=user_id, business_id=user_id, email=email), secret=jwt_secret()
    )
    return {"Authorization": f"Bearer {token}"}


def _seed(session, *, user_id: str = "u1", email: str = "u1@example.co") -> None:
    repo.set_business_name(session, business_id=user_id, name="Acme Ltd")
    repo.save_run(
        session,
        run_id=f"run-{user_id}",
        business_id=user_id,
        as_of=date(2026, 6, 1),
        runway_weeks=9,
        has_shortfall=False,
        minimum_reserve=500.0,
        payload={"business_id": user_id, "weeks": []},
    )
    # an accountant they invited + granted, and access they hold elsewhere
    repo.create_invitation(session, email="acct@firm.co", business_id=user_id, role="accountant")
    repo.add_membership(session, user_id="acct-1", business_id=user_id, role="accountant")
    repo.add_membership(session, user_id=user_id, business_id="client-biz", role="accountant")
    # an invitation addressed to *them* from someone else
    repo.create_invitation(session, email=email, business_id="other-biz", role="accountant")


# --- repository -------------------------------------------------------------


def test_export_account_returns_everything_held() -> None:
    session = next(get_session())
    _seed(session)

    export = repo.export_account(session, user_id="u1", email="u1@example.co")

    assert export["business"]["id"] == "u1"
    assert export["business"]["name"] == "Acme Ltd"
    assert [r["id"] for r in export["runs"]] == ["run-u1"]
    assert export["runs"][0]["payload"] == {"business_id": "u1", "weeks": []}
    assert {m["business_id"] for m in export["memberships"]} == {"client-biz"}
    assert {m["user_id"] for m in export["members"]} == {"acct-1"}
    assert {i["email"] for i in export["invitations_sent"]} == {"acct@firm.co"}


def test_delete_account_erases_the_user_and_only_the_user() -> None:
    session = next(get_session())
    _seed(session, user_id="u1", email="u1@example.co")
    _seed(session, user_id="u2", email="u2@example.co")  # the bystander

    repo.delete_account(session, user_id="u1", email="u1@example.co")

    # u1 fully gone: business, runs, memberships both directions, invitations
    assert repo.get_business(session, "u1") is None
    assert repo.list_runs(session, business_id="u1") == []
    assert repo.list_memberships(session, user_id="u1") == []
    assert repo.get_membership(session, user_id="acct-1", business_id="u1") is None
    assert repo.list_invitations(session, business_id="u1") == []
    # the invitation addressed to u1's email is gone too
    assert all(
        i.email != "u1@example.co" for i in repo.list_invitations(session, business_id="other-biz")
    )
    # u2 untouched
    assert repo.get_business(session, "u2") is not None
    assert len(repo.list_runs(session, business_id="u2")) == 1
    assert repo.get_membership(session, user_id="acct-1", business_id="u2") is not None


def test_delete_account_is_idempotent_and_safe_when_nothing_exists() -> None:
    session = next(get_session())
    repo.delete_account(session, user_id="ghost", email=None)  # no error


# --- API ---------------------------------------------------------------------


def test_export_endpoint_requires_auth_and_downloads_json() -> None:
    assert client.get("/api/account/export").status_code == 401

    session = next(get_session())
    _seed(session)
    response = client.get("/api/account/export", headers=_auth())

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    body = response.json()
    assert body["business"]["id"] == "u1"
    assert body["runs"][0]["id"] == "run-u1"


def test_delete_endpoint_erases_and_returns_204() -> None:
    assert client.delete("/api/account").status_code == 401

    session = next(get_session())
    _seed(session)
    response = client.delete("/api/account", headers=_auth())

    assert response.status_code == 204
    assert client.get("/api/runs", headers=_auth()).json() == []


def test_account_endpoints_ignore_the_switched_business() -> None:
    """An accountant acting on a client's business exports/deletes THEIR OWN
    data, never the client's — X-Business-Id must not change the target."""
    session = next(get_session())
    _seed(session, user_id="owner-1", email="owner@a.co")
    repo.add_membership(session, user_id="acct-9", business_id="owner-1", role="accountant")

    headers = {**_auth(user_id="acct-9", email="acct9@firm.co"), "X-Business-Id": "owner-1"}

    export = client.get("/api/account/export", headers=headers).json()
    assert export["business"]["id"] == "acct-9"  # their own (empty) business

    assert client.delete("/api/account", headers=headers).status_code == 204
    # the client's business survives the accountant deleting their own account
    assert repo.get_business(session, "owner-1") is not None
    assert len(repo.list_runs(session, business_id="owner-1")) == 1
