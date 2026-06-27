"""Behaviour of the HTTP API that exposes the engine to the dashboard."""

import pytest
from fastapi.testclient import TestClient

from cashflow_risk.api import app
from cashflow_risk.auth import Principal, mint_token
from cashflow_risk.auth.settings import jwt_secret

client = TestClient(app)


def _auth(business_id: str = "biz-1") -> dict[str, str]:
    token = mint_token(
        Principal(user_id="u1", business_id=business_id, email="u1@example.co"),
        secret=jwt_secret(),
    )
    return {"Authorization": f"Bearer {token}"}


def test_health_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_returns_a_full_analysis() -> None:
    response = client.post("/api/analyze/demo")

    assert response.status_code == 200
    body = response.json()
    assert len(body["weeks"]) == 13
    assert isinstance(body["top_risks"], list)
    assert body["brief"]["disclaimer"]
    assert "runway_weeks" in body["brief"]


def test_upload_requires_authentication() -> None:
    response = client.post(
        "/api/analyze",
        files={"invoices": ("invoices.csv", "x", "text/csv")},
    )

    assert response.status_code == 401


def test_upload_valid_invoice_csv_is_analysed_and_scoped_to_the_tenant() -> None:
    csv_text = (
        "invoice_id,customer_id,amount,issue_date,due_date\n"
        "INV-1,C1,5000,2026-01-01,2026-01-31\n"
    )

    response = client.post(
        "/api/analyze",
        files={"invoices": ("invoices.csv", csv_text, "text/csv")},
        data={"opening_balance": "1000", "minimum_reserve": "500"},
        headers=_auth(business_id="tenant-a"),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["weeks"]) == 13
    assert body["data_issues"] == []
    assert any(t["invoice_id"] == "INV-1" for t in body["top_risks"])
    assert body["business_id"] == "tenant-a"  # tenant comes from the token


def test_upload_bad_csv_returns_data_issues_not_an_error() -> None:
    response = client.post(
        "/api/analyze",
        files={"invoices": ("bad.csv", "foo,bar\n1,2\n", "text/csv")},
        headers=_auth(),
    )

    assert response.status_code == 200
    body = response.json()
    assert any(i["severity"] == "error" for i in body["data_issues"])
    assert body["top_risks"] == []


def test_dev_token_endpoint_is_disabled_by_default() -> None:
    response = client.post(
        "/api/auth/dev-token",
        json={"email": "a@b.co", "business_id": "biz-1"},
    )

    assert response.status_code == 404


def test_dev_token_when_enabled_mints_a_usable_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CASHFLOW_ALLOW_DEV_TOKEN", "1")

    minted = client.post(
        "/api/auth/dev-token",
        json={"email": "owner@acme.co", "business_id": "acme"},
    )
    assert minted.status_code == 200
    token = minted.json()["access_token"]

    used = client.post(
        "/api/analyze",
        files={"invoices": ("inv.csv", "x", "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert used.status_code == 200
    assert used.json()["business_id"] == "acme"
