"""Behaviour of JWT minting and verification."""

import datetime as dt

import jwt
import pytest

from cashflow_risk.auth import AuthError, Principal, mint_token, verify_token

SECRET = "test-secret-long-enough-for-hs256-aaaa"
PRINCIPAL = Principal(user_id="u1", business_id="biz-1", email="a@b.co")


def test_token_round_trips_the_principal() -> None:
    token = mint_token(PRINCIPAL, secret=SECRET)
    recovered = verify_token(token, secret=SECRET)

    assert recovered.user_id == "u1"
    assert recovered.business_id == "biz-1"
    assert recovered.email == "a@b.co"


def test_expired_token_is_rejected() -> None:
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
    token = mint_token(PRINCIPAL, secret=SECRET, ttl_seconds=60, now=past)

    with pytest.raises(AuthError):
        verify_token(token, secret=SECRET)


def test_token_signed_with_another_secret_is_rejected() -> None:
    token = mint_token(PRINCIPAL, secret="a-different-secret-also-long-enough-bbbb")

    with pytest.raises(AuthError):
        verify_token(token, secret=SECRET)


def test_tampered_token_is_rejected() -> None:
    token = mint_token(PRINCIPAL, secret=SECRET)
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")

    with pytest.raises(AuthError):
        verify_token(tampered, secret=SECRET)


def test_token_missing_tenant_claim_is_rejected() -> None:
    token = jwt.encode({"sub": "u1"}, SECRET, algorithm="HS256")  # no "biz"

    with pytest.raises(AuthError):
        verify_token(token, secret=SECRET)
