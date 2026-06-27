"""Behaviour of the HTTP API that exposes the engine to the dashboard."""

from fastapi.testclient import TestClient

from cashflow_risk.api import app

client = TestClient(app)


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


def test_upload_valid_invoice_csv_is_analysed() -> None:
    csv_text = (
        "invoice_id,customer_id,amount,issue_date,due_date\n"
        "INV-1,C1,5000,2026-01-01,2026-01-31\n"
    )

    response = client.post(
        "/api/analyze",
        files={"invoices": ("invoices.csv", csv_text, "text/csv")},
        data={"opening_balance": "1000", "minimum_reserve": "500"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["weeks"]) == 13
    assert body["data_issues"] == []
    assert any(t["invoice_id"] == "INV-1" for t in body["top_risks"])


def test_upload_bad_csv_returns_data_issues_not_an_error() -> None:
    response = client.post(
        "/api/analyze",
        files={"invoices": ("bad.csv", "foo,bar\n1,2\n", "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert any(i["severity"] == "error" for i in body["data_issues"])
    assert body["top_risks"] == []
