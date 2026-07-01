"""FastAPI dependency that turns a bearer token into a verified Principal.

The active business is the caller's own business by default. To act on another
business, the client sends an ``X-Business-Id`` header; access is allowed only if
the user holds a Membership on that business.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from cashflow_risk.auth.principal import OWNER, Principal
from cashflow_risk.auth.settings import clerk_issuer, clerk_jwks_url, jwt_secret
from cashflow_risk.auth.tokens import AuthError, verify_clerk_token, verify_token
from cashflow_risk.db import get_session
from cashflow_risk.db import repository as repo

_bearer = HTTPBearer(auto_error=False)

BUSINESS_HEADER = "X-Business-Id"


def _resolve_active_business(
    request: Request,
    session: Session,
    *,
    user_id: str,
    own_business: str,
    email: str | None,
) -> Principal:
    requested = request.headers.get(BUSINESS_HEADER) or own_business
    if requested == own_business:
        return Principal(user_id=user_id, business_id=own_business, email=email, role=OWNER)

    membership = repo.get_membership(session, user_id=user_id, business_id=requested)
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this business")
    return Principal(user_id=user_id, business_id=requested, email=email, role=membership.role)


def require_principal(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
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
            # Production: Clerk token. The user's own business id is their user id.
            identity = verify_clerk_token(token, jwks_url=jwks_url, issuer=clerk_issuer())
            return _resolve_active_business(
                request, session, user_id=identity.user_id,
                own_business=identity.user_id, email=identity.email,
            )
        principal = verify_token(token, secret=jwt_secret())
        return _resolve_active_business(
            request, session, user_id=principal.user_id,
            own_business=principal.business_id, email=principal.email,
        )
    except AuthError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
