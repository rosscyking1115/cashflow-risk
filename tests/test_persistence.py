"""Persistence + tenant isolation at the data layer.

Authenticated analyses are stored and retrievable, and one tenant can never see
another tenant's runs — even with the exact run id.
"""

import pytest
from fastapi.testclient import TestClient

from cashflow_risk.api import app
from cashflow_risk.auth import Principal, mint_token
from cashflow_risk.auth.settings import jwt_secret
from cashflow_risk.db.session import DEFAULT_URL, _database_url

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


# --- the production guard against the rejected SQLite fallback -----------------


def test_production_refuses_to_start_without_a_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Removing the blueprint's database binding made an unset DATABASE_URL a real
    misconfiguration, not a theoretical one. Production must fail loudly rather
    than quietly serve from a file the host discards on every redeploy."""
    monkeypatch.setenv("CASHFLOW_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="refuses|Refusing"):
        _database_url()


def test_production_refuses_an_explicit_sqlite_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting DATABASE_URL to SQLite is the same defect, just spelled out."""
    monkeypatch.setenv("CASHFLOW_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./cashflow.db")
    with pytest.raises(RuntimeError, match="Refusing"):
        _database_url()


def test_production_accepts_a_postgres_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard must not block the configuration it exists to require."""
    monkeypatch.setenv("CASHFLOW_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@example.test/db")
    assert _database_url() == "postgresql+psycopg://u:p@example.test/db"


def test_dev_still_falls_back_to_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard is production-only; local development keeps working with nothing set."""
    monkeypatch.delenv("CASHFLOW_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _database_url() == DEFAULT_URL
