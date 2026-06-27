"""Test configuration: use an in-memory SQLite DB and reset it per test."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite://")  # in-memory, before app import

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402

from cashflow_risk.db import models  # noqa: E402,F401  (register tables on Base)
from cashflow_risk.db.base import Base  # noqa: E402
from cashflow_risk.db.session import get_engine  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db() -> Iterator[None]:
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
