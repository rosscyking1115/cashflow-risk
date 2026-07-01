"""Refresh cached Companies House signals for every known company.

    uv run python scripts/refresh_signals.py

Run daily by a Render Cron job. Re-fetches each cached company's public profile
and upserts the current signals, so filing/overdue/insolvency changes flow into
the risk score. A clean no-op when COMPANIES_HOUSE_API_KEY is unset.
"""

from __future__ import annotations

from cashflow_risk.db import get_session
from cashflow_risk.enrichment.refresh import refresh_all_signals
from cashflow_risk.enrichment.service import companies_house_api_key


def main() -> int:
    api_key = companies_house_api_key()
    if not api_key:
        print("COMPANIES_HOUSE_API_KEY not set — nothing to refresh.")
        return 0
    session = next(get_session())
    try:
        result = refresh_all_signals(session, api_key=api_key)
    finally:
        session.close()
    print(
        f"Companies House refresh: {result.refreshed} refreshed, "
        f"{result.not_found} not found, {result.errors} errors "
        f"(of {result.total} cached)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
