"""The authenticated caller and the tenant they belong to."""

from __future__ import annotations

from pydantic import BaseModel


class Principal(BaseModel):
    """An authenticated user, bound to exactly one Business (the tenant).

    ``business_id`` is the tenant scope for every request. It comes from the
    verified token, never from client input.
    """

    user_id: str
    business_id: str
    email: str | None = None
