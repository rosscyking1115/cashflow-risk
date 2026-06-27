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
    """The configured URL, normalised to a driver SQLAlchemy understands.

    Managed Postgres (Render/Heroku) hands out ``postgres://``; SQLAlchemy needs
    an explicit dialect+driver, so we map Postgres URLs onto psycopg v3.
    """
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


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
    """Create tables for local SQLite (dev/test). Managed databases use Alembic
    migrations (``alembic upgrade head``), so this is a no-op for non-SQLite."""
    from cashflow_risk.db import models  # noqa: F401

    engine = get_engine()
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()
