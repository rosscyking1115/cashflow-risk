"""Companies House Public Data API client + signal interpretation.

Reads a company's profile (one call gives statutory deadlines, overdue flags, and
insolvency/charges links) and turns it into a small set of late-payment risk
signals. Free, read-only, API-key over HTTP Basic auth. Companies + LLPs only —
sole traders are not on Companies House, so this never applies to them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx

BASE_URL = "https://api.company-information.service.gov.uk"


@dataclass(frozen=True)
class CompanySignals:
    """Late-payment-relevant facts about a company, from its public profile."""

    company_number: str
    status: str | None
    accounts_overdue: bool
    accounts_next_due: date | None
    confirmation_overdue: bool
    has_insolvency: bool
    has_charges: bool


def _parse_date(value: object) -> date | None:
    if isinstance(value, str) and value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def parse_company_profile(company_number: str, profile: dict[str, Any]) -> CompanySignals:
    """Map a Companies House company profile onto :class:`CompanySignals`.

    Uses the non-deprecated fields: ``accounts.next_accounts.*`` and
    ``confirmation_statement.*``; presence of ``links.insolvency`` / ``links.charges``.
    """
    accounts = profile.get("accounts") or {}
    next_accounts = accounts.get("next_accounts") or {}
    confirmation = profile.get("confirmation_statement") or {}
    links = profile.get("links") or {}
    return CompanySignals(
        company_number=company_number,
        status=profile.get("company_status"),
        accounts_overdue=bool(next_accounts.get("overdue")),
        accounts_next_due=_parse_date(next_accounts.get("due_on")),
        confirmation_overdue=bool(confirmation.get("overdue")),
        has_insolvency="insolvency" in links,
        has_charges="charges" in links,
    )


def fetch_company_signals(
    company_number: str, *, api_key: str, client: httpx.Client | None = None
) -> CompanySignals | None:
    """Fetch and parse a company's signals. Returns None if not found (404).

    A ``client`` may be injected (for tests); otherwise one is created with the
    API key as the HTTP Basic username and a blank password.
    """
    owns_client = client is None
    http = client or httpx.Client(base_url=BASE_URL, auth=(api_key, ""), timeout=15.0)
    try:
        response = http.get(f"/company/{company_number}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return parse_company_profile(company_number, response.json())
    finally:
        if owns_client:
            http.close()


# Log-odds contributions added to the late-payment score. Overdue filings are the
# truest *early* signal; insolvency is the strongest (but latest) red flag.
def filing_risk_logit(signals: CompanySignals) -> float:
    logit = 0.0
    if signals.accounts_overdue:
        logit += 0.8
    if signals.confirmation_overdue:
        logit += 0.5
    if signals.has_charges:
        logit += 0.3
    if signals.has_insolvency:
        logit += 2.0
    if signals.status and signals.status != "active":
        logit += 1.0
    return logit


def filing_risk_drivers(signals: CompanySignals) -> list[str]:
    drivers: list[str] = []
    if signals.has_insolvency:
        drivers.append("Customer has an insolvency case at Companies House")
    if signals.accounts_overdue:
        drivers.append("Customer's accounts are overdue at Companies House")
    if signals.confirmation_overdue:
        drivers.append("Customer's confirmation statement is overdue")
    if signals.has_charges:
        drivers.append("Customer has registered charges (secured borrowing)")
    if signals.status and signals.status != "active":
        drivers.append(f"Customer's company status is '{signals.status}'")
    return drivers
