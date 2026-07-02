"""Daily maintenance: retention purge + Companies House signal refresh.

    uv run python scripts/daily_maintenance.py

Run daily by the Render Cron job (one job does both — cron services are billed
per service, and neither task justifies its own). Each step is independent and
best-effort: a failure in one is reported but does not block the other.

- **Retention purge**: analysis runs and audit events older than
  ``CASHFLOW_RETENTION_DAYS`` (default 730 — the 24 months promised in
  docs/privacy-notice.md) are deleted. Set to 0 to disable.
- **Signal refresh**: re-fetches every cached company's Companies House signals
  (see cashflow_risk.enrichment.refresh). Skipped without an API key.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from cashflow_risk.db import get_session
from cashflow_risk.db import repository as repo
from cashflow_risk.enrichment.refresh import refresh_all_signals
from cashflow_risk.enrichment.service import companies_house_api_key

RETENTION_ENV = "CASHFLOW_RETENTION_DAYS"
DEFAULT_RETENTION_DAYS = 730  # 24 months, per the privacy notice


def retention_days() -> int:
    raw = os.environ.get(RETENTION_ENV, "")
    try:
        return int(raw) if raw else DEFAULT_RETENTION_DAYS
    except ValueError:
        print(f"Ignoring invalid {RETENTION_ENV}={raw!r}; using {DEFAULT_RETENTION_DAYS}.")
        return DEFAULT_RETENTION_DAYS


def main() -> int:
    session = next(get_session())
    failures = 0
    try:
        days = retention_days()
        if days > 0:
            try:
                cutoff = datetime.now(UTC) - timedelta(days=days)
                runs, events = repo.purge_expired(session, cutoff=cutoff)
                print(f"Retention purge ({days}d): {runs} runs, {events} audit events removed.")
            except Exception as exc:  # keep going — the refresh must still run
                failures += 1
                print(f"Retention purge FAILED: {exc!r}")
        else:
            print(f"Retention purge disabled ({RETENTION_ENV}=0).")

        api_key = companies_house_api_key()
        if api_key:
            try:
                result = refresh_all_signals(session, api_key=api_key)
                print(
                    f"Companies House refresh: {result.refreshed} refreshed, "
                    f"{result.not_found} not found, {result.errors} errors "
                    f"(of {result.total} cached)."
                )
            except Exception as exc:
                failures += 1
                print(f"Companies House refresh FAILED: {exc!r}")
        else:
            print("COMPANIES_HOUSE_API_KEY not set — signal refresh skipped.")
    finally:
        session.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
