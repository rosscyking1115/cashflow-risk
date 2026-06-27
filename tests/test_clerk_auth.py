"""Clerk (RS256 / JWKS) verification and the authenticated upload path.

Uses a locally generated RSA keypair and a stubbed JWKS client, so the Clerk
verification logic is exercised without any network or real Clerk account.
"""

import datetime as dt
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from cashflow_risk.api import app
from cashflow_risk.auth import AuthError, tokens
from cashflow_risk.auth.tokens import _decode_clerk

client = TestClient(app)


@pytest.fixture(scope="module")
def keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _clerk_token(private: rsa.RSAPrivateKey, **claims: object) -> str:
    payload: dict[str, object] = {
        "sub": "user_abc",
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    }
    payload.update(claims)
    return jwt.encode(payload, private, algorithm="RS256")


def test_decode_clerk_extracts_identity(keypair) -> None:
    private, public = keypair
    token = _clerk_token(private, sub="user_abc", email="owner@acme.co")

    identity = _decode_clerk(token, public, issuer=None)

    assert identity.user_id == "user_abc"
    assert identity.email == "owner@acme.co"


def test_decode_clerk_rejects_expired(keypair) -> None:
    private, public = keypair
    token = _clerk_token(private, exp=dt.datetime.now(dt.UTC) - dt.timedelta(hours=1))

    with pytest.raises(AuthError):
        _decode_clerk(token, public, issuer=None)


def test_decode_clerk_rejects_wrong_issuer(keypair) -> None:
    private, public = keypair
    token = _clerk_token(private, iss="https://real.clerk")

    with pytest.raises(AuthError):
        _decode_clerk(token, public, issuer="https://expected.clerk")


def test_upload_accepts_a_valid_clerk_token(keypair, monkeypatch: pytest.MonkeyPatch) -> None:
    private, public = keypair
    monkeypatch.setenv("CLERK_JWKS_URL", "https://stub/.well-known/jwks.json")
    monkeypatch.setattr(
        tokens, "_jwks_client", lambda url: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public)
        )
    )
    token = _clerk_token(private, sub="clerk_user_1", email="u@acme.co")

    response = client.post(
        "/api/analyze",
        files={"invoices": ("inv.csv", "invoice_id,customer_id,amount,issue_date,due_date\n"
                            "INV-1,C1,1000,2026-01-01,2026-01-31\n", "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["business_id"] == "clerk_user_1"  # tenant = Clerk user

    runs = client.get("/api/runs", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(runs) == 1


def test_invalid_clerk_token_is_rejected(keypair, monkeypatch: pytest.MonkeyPatch) -> None:
    _, public = keypair
    monkeypatch.setenv("CLERK_JWKS_URL", "https://stub/.well-known/jwks.json")
    monkeypatch.setattr(
        tokens, "_jwks_client", lambda url: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public)
        )
    )

    response = client.post(
        "/api/analyze",
        files={"invoices": ("inv.csv", "x", "text/csv")},
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401
