"""Daily refresh of cached Companies House signals.

The signal cache (``company_signals``) is otherwise fetch-once — it goes stale as
companies file accounts, fall overdue, or enter insolvency. This worker re-fetches
every cached company's public profile and upserts the current signals, so those
changes flow into the late-payment risk score on the next analysis.

Deliberately plain functions (no scheduler framework): a Render Cron job calls
:func:`refresh_all_signals` daily. If this grows into a multi-stage DAG it can be
wrapped in Prefect/Dagster later — the function stays the unit of work.

Resilient by design: a single reused HTTP client for the whole batch (kind to the
600 req / 5 min rate limit), and a per-company try/except so one bad fetch never
aborts the run. A failed or missing company keeps its previously cached signals.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from cashflow_risk.db import repository as repo
from cashflow_risk.enrichment.companies_house import BASE_URL, fetch_company_signals


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of one refresh run, for logging and cron visibility."""

    total: int
    refreshed: int
    not_found: int
    errors: int


def refresh_all_signals(
    session: Session, *, api_key: str, client: httpx.Client | None = None
) -> RefreshResult:
    """Re-fetch and upsert signals for every cached company number.

    A ``client`` may be injected (for tests); otherwise one is created and reused
    across the whole batch, with the API key as HTTP Basic username.
    """
    numbers = repo.all_company_numbers(session)
    owns_client = client is None
    http = client or httpx.Client(base_url=BASE_URL, auth=(api_key, ""), timeout=15.0)
    refreshed = not_found = errors = 0
    try:
        for number in numbers:
            try:
                signals = fetch_company_signals(number, api_key=api_key, client=http)
            except Exception:  # keep going — one bad company must not abort the batch
                errors += 1
                continue
            if signals is None:  # 404: gone from Companies House; keep the last known state
                not_found += 1
                continue
            repo.upsert_company_signals(session, signals)
            refreshed += 1
    finally:
        if owns_client:
            http.close()
    return RefreshResult(
        total=len(numbers), refreshed=refreshed, not_found=not_found, errors=errors
    )
