"""Upload hardening on /api/analyze (docs/security_privacy.md enforcement list).

Size and row limits protect the service; content sniffing protects the user
(clear message instead of a garbage parse). Browser MIME headers are not
trusted — the bytes themselves are checked.
"""

import pytest
from fastapi.testclient import TestClient

from cashflow_risk.api import app, upload_guard
from cashflow_risk.auth import Principal, mint_token
from cashflow_risk.auth.settings import jwt_secret

client = TestClient(app)

HEADER = "invoice_id,customer_id,amount,issue_date,due_date\n"


def _auth() -> dict[str, str]:
    token = mint_token(
        Principal(user_id="u1", business_id="u1", email="u1@example.co"), secret=jwt_secret()
    )
    return {"Authorization": f"Bearer {token}"}


def _post(content: bytes | str, filename: str = "invoices.csv") -> object:
    return client.post(
        "/api/analyze",
        files={"invoices": (filename, content, "text/csv")},
        headers=_auth(),
    )


def test_oversized_upload_is_rejected_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload_guard, "MAX_UPLOAD_BYTES", 1024)

    response = _post(HEADER + "INV-1,C1,100,2026-01-01,2026-01-31\n" * 100)

    assert response.status_code == 413
    assert "large" in response.json()["detail"].lower()


def test_too_many_rows_is_rejected_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload_guard, "MAX_ROWS", 5)

    rows = "".join(f"INV-{i},C1,100,2026-01-01,2026-01-31\n" for i in range(10))
    response = _post(HEADER + rows)

    assert response.status_code == 413
    assert "rows" in response.json()["detail"].lower()


def test_xlsx_masquerading_as_csv_gets_a_helpful_message() -> None:
    response = _post(b"PK\x03\x04 fake zip bytes", filename="ledger.csv")

    assert response.status_code == 415
    assert "csv" in response.json()["detail"].lower()  # tells them to export as CSV


def test_binary_content_is_rejected_415() -> None:
    response = _post(b"\x00\x01\x02\x03 not text at all")

    assert response.status_code == 415


def test_empty_upload_is_rejected_422() -> None:
    response = _post("   \n  ")

    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_normal_csv_still_works_and_bom_is_tolerated() -> None:
    csv_text = "﻿" + HEADER + "INV-1,C1,5000,2026-01-01,2026-01-31\n"

    response = _post(csv_text.encode("utf-8"))

    assert response.status_code == 200
    assert any(t["invoice_id"] == "INV-1" for t in response.json()["top_risks"])
