"""Engine and session management.

DB-agnostic: ``DATABASE_URL`` defaults to a local SQLite file for dev, and points
at Postgres in production. Tables are created via :func:`init_db` (Alembic
migrations are the production follow-up).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cashflow_risk.db.base import Base

DEFAULT_URL = "sqlite:///./cashflow.db"


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = _database_url()
    if url.startswith("sqlite"):
        in_memory = url in ("sqlite://", "sqlite:///:memory:")
        connect_args = {"check_same_thread": False}
        if in_memory:
            # one shared connection so the in-memory schema survives across threads
            return create_engine(url, connect_args=connect_args, poolclass=StaticPool)
        return create_engine(url, connect_args=connect_args)
    return create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def init_db() -> None:
    """Create tables that don't yet exist. Import models so they're registered."""
    from cashflow_risk.db import models  # noqa: F401

    Base.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()
