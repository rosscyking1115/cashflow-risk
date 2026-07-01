"""Resolve Companies House signals for a set of company numbers.

Cache-first (reads the ``company_signals`` table), fetching any that are missing
when an API key is configured, and caching the result. Best-effort: any fetch
error is swallowed so enrichment never fails the analysis.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from sqlalchemy.orm import Session

from cashflow_risk.db import repository as repo
from cashflow_risk.enrichment.companies_house import CompanySignals, fetch_company_signals


def companies_house_api_key() -> str | None:
    return os.environ.get("COMPANIES_HOUSE_API_KEY") or None


def signals_for(
    session: Session, company_numbers: Iterable[str | None], *, api_key: str | None = None
) -> dict[str, CompanySignals]:
    result: dict[str, CompanySignals] = {}
    for number in {n for n in company_numbers if n}:
        cached = repo.get_company_signals(session, number)
        if cached is not None:
            result[number] = cached
            continue
        if api_key:
            try:
                fetched = fetch_company_signals(number, api_key=api_key)
            except Exception:  # enrichment is optional — never break the analysis
                continue
            if fetched is not None:
                repo.upsert_company_signals(session, fetched)
                result[number] = fetched
    return result
