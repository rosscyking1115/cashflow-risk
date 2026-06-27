"""HTTP API for the cashflow-risk engine. Run with ``uvicorn cashflow_risk.api:app``."""

from cashflow_risk.api.app import app

__all__ = ["app"]
