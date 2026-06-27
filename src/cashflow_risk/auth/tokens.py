"""JWT minting and verification.

Standards-based (PyJWT), not hand-rolled crypto. Symmetric HS256 today; a hosted
IdP slots in by changing ``verify_token`` to fetch the provider's JWKS and verify
RS256 — call sites and the :class:`Principal` shape stay the same.
"""

from __future__ import annotations

import datetime as dt

import jwt

from cashflow_risk.auth.principal import Principal

ALGORITHM = "HS256"


class AuthError(Exception):
    """Token missing, invalid, expired, or tampered with."""


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
