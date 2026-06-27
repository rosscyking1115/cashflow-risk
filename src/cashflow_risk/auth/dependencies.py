"""FastAPI dependency that turns a bearer token into a verified Principal."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cashflow_risk.auth.principal import Principal
from cashflow_risk.auth.settings import clerk_issuer, clerk_jwks_url, jwt_secret
from cashflow_risk.auth.tokens import AuthError, verify_clerk_token, verify_token

_bearer = HTTPBearer(auto_error=False)


def require_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        jwks_url = clerk_jwks_url()
        if jwks_url is not None:
            # Production: Clerk-issued token. Each user is their own tenant; the
            # Business row is created lazily on first analysis (ensure_business).
            identity = verify_clerk_token(token, jwks_url=jwks_url, issuer=clerk_issuer())
            return Principal(
                user_id=identity.user_id,
                business_id=identity.user_id,
                email=identity.email,
            )
        return verify_token(token, secret=jwt_secret())
    except AuthError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
