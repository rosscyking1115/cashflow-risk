"""JWT minting and verification.

Standards-based (PyJWT), not hand-rolled crypto. Symmetric HS256 today; a hosted
IdP slots in by changing ``verify_token`` to fetch the provider's JWKS and verify
RS256 — call sites and the :class:`Principal` shape stay the same.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt

from cashflow_risk.auth.principal import Principal

ALGORITHM = "HS256"


class AuthError(Exception):
    """Token missing, invalid, expired, or tampered with."""


@dataclass(frozen=True)
class ClerkIdentity:
    """The authenticated identity extracted from a Clerk session token."""

    user_id: str
    email: str | None = None


def mint_token(
    principal: Principal,
    *,
    secret: str,
    ttl_seconds: int = 3600,
    now: dt.datetime | None = None,
) -> str:
    issued = now or dt.datetime.now(dt.UTC)
    payload = {
        "sub": principal.user_id,
        "biz": principal.business_id,
        "email": principal.email,
        "iat": int(issued.timestamp()),
        "exp": int((issued + dt.timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_token(token: str, *, secret: str) -> Principal:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc

    sub = payload.get("sub")
    biz = payload.get("biz")
    if not sub or not biz:
        raise AuthError("token missing required claims")
    return Principal(user_id=str(sub), business_id=str(biz), email=payload.get("email"))


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url)


def _decode_clerk(token: str, key: Any, issuer: str | None) -> ClerkIdentity:
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc

    sub = payload.get("sub")
    if not sub:
        raise AuthError("token missing subject")
    return ClerkIdentity(user_id=str(sub), email=payload.get("email"))


def verify_clerk_token(token: str, *, jwks_url: str, issuer: str | None = None) -> ClerkIdentity:
    """Verify a Clerk session JWT against Clerk's JWKS (RS256)."""
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
    except Exception as exc:  # network, malformed token, unknown kid -> deny
        raise AuthError(str(exc)) from exc
    return _decode_clerk(token, signing_key.key, issuer)
