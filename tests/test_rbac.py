"""Role-based access across businesses.

A user owns their own business. An owner can grant another user a role on it
(e.g. an accountant), who then gets read access via the X-Business-Id header —
but not write. Non-members are refused.
"""

from fastapi.testclient import TestClient

from cashflow_risk.api import app
from cashflow_risk.auth import Principal, mint_token
from cashflow_risk.auth.settings import jwt_secret

client = TestClient(app)

CSV = (
    "invoice_id,customer_id,amount,issue_date,due_date\n"
    "INV-1,Acme,5000,2026-01-01,2026-01-31\n"
)


def _token(user: str, email: str | None = None) -> str:
    # own business id == user id, matching the production (Clerk) model
    return mint_token(
        Principal(user_id=user, business_id=user, email=email or f"{user}@x.co"),
        secret=jwt_secret(),
    )


def _auth(user: str, acting_as: str | None = None, email: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_token(user, email)}"}
    if acting_as:
        headers["X-Business-Id"] = acting_as
    return headers


def _upload(user: str, acting_as: str | None = None):
    return client.post(
        "/api/analyze",
        files={"invoices": ("i.csv", CSV, "text/csv")},
        data={"opening_balance": "5000", "minimum_reserve": "2000"},
        headers=_auth(user, acting_as),
    )


def _grant(owner: str, member: str, role: str):
    return client.post(
        f"/api/businesses/{owner}/members",
        json={"user_id": member, "role": role},
        headers=_auth(owner),
    )


def test_non_member_cannot_access_another_business() -> None:
    _upload("owner1")
    response = client.get("/api/runs", headers=_auth("stranger", acting_as="owner1"))
    assert response.status_code == 403


def test_owner_can_grant_accountant_read_access() -> None:
    run_id = _upload("owner2").json()["run_id"]

    assert _grant("owner2", "acct2", "accountant").status_code == 200

    runs = client.get("/api/runs", headers=_auth("acct2", acting_as="owner2"))
    assert runs.status_code == 200
    assert any(r["id"] == run_id for r in runs.json())


def test_accountant_is_read_only() -> None:
    _grant("owner3", "acct3", "accountant")
    # can read owner3's data, but cannot upload to it
    assert _upload("acct3", acting_as="owner3").status_code == 403


def test_only_an_owner_can_add_members() -> None:
    _grant("owner4", "acct4", "accountant")
    # the accountant tries to add another member to owner4 -> refused
    refused = client.post(
        "/api/businesses/owner4/members",
        json={"user_id": "intruder", "role": "accountant"},
        headers=_auth("acct4"),
    )
    assert refused.status_code == 403


def test_list_businesses_shows_own_and_granted() -> None:
    _grant("owner5", "acct5", "accountant")

    businesses = client.get("/api/businesses", headers=_auth("acct5")).json()
    roles = {b["business_id"]: b["role"] for b in businesses}

    assert roles["acct5"] == "owner"  # their own business
    assert roles["owner5"] == "accountant"  # access granted by owner5


def test_invitation_by_email_is_claimed_on_login() -> None:
    # owner invites an accountant by email (mixed case, to check normalisation)
    invited = client.post(
        "/api/businesses/owner6/invitations",
        json={"email": "Book.Keeper@Firm.com", "role": "accountant"},
        headers=_auth("owner6"),
    )
    assert invited.status_code == 200

    # the invited person signs in (matching email) and lists businesses -> claimed
    acct = _auth("acct6", email="book.keeper@firm.com")
    businesses = client.get("/api/businesses", headers=acct).json()
    roles = {b["business_id"]: b["role"] for b in businesses}
    assert roles.get("owner6") == "accountant"

    # and can now read owner6's data
    reading = _auth("acct6", acting_as="owner6", email="book.keeper@firm.com")
    assert client.get("/api/runs", headers=reading).status_code == 200


def test_owner_can_name_their_business() -> None:
    named = client.put("/api/businesses/owner8", json={"name": "Acme Ltd"}, headers=_auth("owner8"))
    assert named.status_code == 200
    assert named.json()["name"] == "Acme Ltd"

    businesses = client.get("/api/businesses", headers=_auth("owner8")).json()
    own = next(b for b in businesses if b["business_id"] == "owner8")
    assert own["name"] == "Acme Ltd"


def test_non_owner_cannot_rename_a_business() -> None:
    _grant("owner9", "acct9", "accountant")
    refused = client.put("/api/businesses/owner9", json={"name": "Hax"}, headers=_auth("acct9"))
    assert refused.status_code == 403


def test_only_an_owner_can_invite() -> None:
    _grant("owner7", "acct7", "accountant")
    refused = client.post(
        "/api/businesses/owner7/invitations",
        json={"email": "x@y.com", "role": "accountant"},
        headers=_auth("acct7"),
    )
    assert refused.status_code == 403
