"""The authenticated caller and the tenant they belong to."""

from __future__ import annotations

from pydantic import BaseModel

OWNER = "owner"
ACCOUNTANT = "accountant"
ROLES = {OWNER, ACCOUNTANT}


class Principal(BaseModel):
    """An authenticated user acting on one Business (the tenant).

    ``business_id`` is the *active* tenant scope for the request — the user's own
    business by default, or another business they've been granted access to.
    ``role`` is their role on that business (owner has read+write; accountant is
    read-only). It comes from the verified token and membership, never client input.
    """

    user_id: str
    business_id: str
    email: str | None = None
    role: str = OWNER
