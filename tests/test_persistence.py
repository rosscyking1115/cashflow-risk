"""Persistence + tenant isolation at the data layer.

Authenticated analyses are stored and retrievable, and one tenant can never see
another tenant's runs — even with the exact run id.
"""

from fastapi.testclient import TestClient

from cashflow_risk.api import app
from cashflow_risk.auth import Principal, mint_token
from cashflow_risk.auth.settings import jwt_secret

client = TestClient(app)

CSV = (
    "invoice_id,customer_id,amount,issue_date,due_date\n"
    "INV-1,C1,5000,2026-01-01,2026-01-31\n"
)


def _auth(business_id: str) -> dict[str, str]:
    token = mint_token(
        Principal(user_id="u1", business_id=business_id, email="u1@example.co"),
        secret=jwt_secret(),
    )
    return {"Authorization": f"Bearer {token}"}


def _upload(business_id: str):
    return client.post(
        "/api/analyze",
        files={"invoices": ("inv.csv", CSV, "text/csv")},
        data={"opening_balance": "1000", "minimum_reserve": "500"},
        headers=_auth(business_id),
    )


def test_analysis_is_persisted_and_listed() -> None:
    assert client.get("/api/runs", headers=_auth("acme")).json() == []

    run_id = _upload("acme").json()["run_id"]
    assert run_id

    runs = client.get("/api/runs", headers=_auth("acme")).json()
    assert len(runs) == 1
    assert runs[0]["id"] == run_id
    assert runs[0]["runway_weeks"] == 13


def test_run_detail_round_trips() -> None:
    run_id = _upload("acme").json()["run_id"]

    detail = client.get(f"/api/runs/{run_id}", headers=_auth("acme"))

    assert detail.status_code == 200
    body = detail.json()
    assert body["run_id"] == run_id
    assert len(body["weeks"]) == 13


def test_one_tenant_cannot_see_anothers_runs() -> None:
    run_id = _upload("tenant-a").json()["run_id"]

    assert client.get("/api/runs", headers=_auth("tenant-b")).json() == []
    assert client.get(f"/api/runs/{run_id}", headers=_auth("tenant-b")).status_code == 404
    assert client.get(f"/api/runs/{run_id}", headers=_auth("tenant-a")).status_code == 200


def test_runs_endpoints_require_auth() -> None:
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs/anything").status_code == 401
