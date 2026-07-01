"""Sentry with PII scrubbing (DPIA R3) + the no-sensitive-logs guarantee.

The scrubber is a pure function tested directly; init is config-only; and the
log-hygiene test uploads a ledger with marker values and asserts none of them
reach any log record — the enforcement docs/security_privacy.md promises.
"""

import logging

import pytest
import sentry_sdk
from fastapi.testclient import TestClient

from cashflow_risk.api import app
from cashflow_risk.auth import Principal, mint_token
from cashflow_risk.auth.settings import jwt_secret
from cashflow_risk.observability import REDACTED, init_sentry, scrub_event

client = TestClient(app)


def _auth(business_id: str = "biz-1") -> dict[str, str]:
    token = mint_token(
        Principal(user_id="u1", business_id=business_id, email="u1@example.co"),
        secret=jwt_secret(),
    )
    return {"Authorization": f"Bearer {token}"}


# --- the scrubber ---------------------------------------------------------


def test_scrub_redacts_financial_and_identity_keys_recursively() -> None:
    event = {
        "extra": {
            "amount": 98765.43,
            "customer_name": "Sensitive Widgets Ltd",
            "detail": {"opening_balance": 1000, "invoices": ["INV-1"], "week": 3},
        },
        "contexts": {"custom": {"email": "owner@acme.co", "company_number": "12345678"}},
    }

    scrubbed = scrub_event(event, {})

    assert scrubbed is not None
    assert scrubbed["extra"]["amount"] == REDACTED
    assert scrubbed["extra"]["customer_name"] == REDACTED
    assert scrubbed["extra"]["detail"]["opening_balance"] == REDACTED
    assert scrubbed["extra"]["detail"]["invoices"] == REDACTED
    assert scrubbed["extra"]["detail"]["week"] == 3  # non-sensitive survives
    assert scrubbed["contexts"]["custom"]["email"] == REDACTED
    assert scrubbed["contexts"]["custom"]["company_number"] == REDACTED


def test_scrub_drops_request_bodies_and_auth_headers_but_keeps_frames() -> None:
    event = {
        "request": {
            "url": "https://api.example/api/analyze",
            "method": "POST",
            "data": "invoice_id,customer_id,amount\nINV-1,Acme,5000\n",
            "cookies": {"session": "abc"},
            "headers": {"Authorization": "Bearer xyz", "Content-Type": "text/csv"},
        },
        "exception": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [{"filename": "app.py", "function": "analyze", "lineno": 7}]
                    }
                }
            ]
        },
    }

    scrubbed = scrub_event(event, {})

    assert scrubbed is not None
    assert "data" not in scrubbed["request"]  # never ship an uploaded ledger
    assert "cookies" not in scrubbed["request"]
    assert scrubbed["request"]["headers"]["Authorization"] == REDACTED
    assert scrubbed["request"]["headers"]["Content-Type"] == "text/csv"
    frame = scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert frame["filename"] == "app.py"  # stack traces stay useful


# --- init -----------------------------------------------------------------


def test_init_without_dsn_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry() is False


def test_init_with_dsn_configures_a_no_pii_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/0")
    try:
        assert init_sentry() is True
        options = sentry_sdk.get_client().options
        assert options["send_default_pii"] is False
        assert options["include_local_variables"] is False  # locals carry ledgers
        assert options["max_request_body_size"] == "never"
        assert options["before_send"] is scrub_event
    finally:
        sentry_sdk.get_client().close()  # don't leak an active client to other tests


# --- no-sensitive-logs enforcement (DPIA R3) --------------------------------


def test_upload_never_leaks_financial_data_into_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    csv_text = (
        "invoice_id,customer_id,amount,issue_date,due_date\n"
        "INV-9,Sensitive Widgets Ltd,98765.43,2026-01-01,2026-01-31\n"
    )

    response = client.post(
        "/api/analyze",
        files={"invoices": ("invoices.csv", csv_text, "text/csv")},
        headers=_auth(),
    )
    assert response.status_code == 200

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "Sensitive Widgets Ltd" not in logged
    assert "98765.43" not in logged
    assert "INV-9" not in logged
