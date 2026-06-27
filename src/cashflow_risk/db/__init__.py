"""Persistence layer. PostgreSQL in production, SQLite for local dev and tests.

Tenant isolation is enforced in :mod:`cashflow_risk.db.repository` — every query
is scoped to a ``business_id``.
"""

from cashflow_risk.db.session import get_session, init_db

__all__ = ["get_session", "init_db"]
