"""Companies House client, signal interpretation, and caching — against mocks."""

from datetime import date

import httpx

from cashflow_risk.db import get_session
from cashflow_risk.db import repository as repo
from cashflow_risk.enrichment.companies_house import (
    BASE_URL,
    CompanySignals,
    fetch_company_signals,
    filing_risk_drivers,
    filing_risk_logit,
    parse_company_profile,
)

PROFILE = {
    "company_status": "active",
    "accounts": {"next_accounts": {"due_on": "2026-09-30", "overdue": True}},
    "confirmation_statement": {"overdue": False},
    "links": {"self": "/company/12345678", "charges": "/company/12345678/charges"},
}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL, auth=("k", ""))


def test_parse_profile_extracts_signals() -> None:
    signals = parse_company_profile("12345678", PROFILE)

    assert signals.accounts_overdue is True
    assert signals.accounts_next_due == date(2026, 9, 30)
    assert signals.confirmation_overdue is False
    assert signals.has_charges is True
    assert signals.has_insolvency is False


def test_parse_profile_tolerates_missing_fields() -> None:
    signals = parse_company_profile("00000006", {})

    assert signals.status is None
    assert signals.accounts_overdue is False
    assert signals.accounts_next_due is None
    assert signals.has_charges is False


def test_fetch_returns_signals_and_none_for_unknown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/company/12345678":
            return httpx.Response(200, json=PROFILE)
        return httpx.Response(404)

    assert fetch_company_signals("12345678", api_key="k", client=_client(handler)).accounts_overdue
    assert fetch_company_signals("99999999", api_key="k", client=_client(handler)) is None


def test_filing_risk_logit_orders_by_severity() -> None:
    clean = CompanySignals("1", "active", False, None, False, False, False)
    risky = CompanySignals("2", "active", True, None, True, True, True)
    insolvent = CompanySignals("3", "active", False, None, False, True, False)

    assert filing_risk_logit(clean) == 0.0
    assert filing_risk_logit(risky) > filing_risk_logit(clean)
    assert filing_risk_logit(insolvent) >= 2.0
    assert any("insolvency" in d.lower() for d in filing_risk_drivers(insolvent))


def test_signals_cache_round_trips() -> None:
    session = next(get_session())
    signals = CompanySignals("00000006", "active", True, date(2026, 9, 30), False, False, True)

    repo.upsert_company_signals(session, signals)
    assert repo.get_company_signals(session, "00000006") == signals

    updated = CompanySignals("00000006", "dissolved", False, None, False, True, True)
    repo.upsert_company_signals(session, updated)
    assert repo.get_company_signals(session, "00000006") == updated


def test_signals_for_reads_cache_and_skips_uncached_without_key() -> None:
    from cashflow_risk.enrichment.service import signals_for

    session = next(get_session())
    repo.upsert_company_signals(
        session, CompanySignals("00000006", "active", True, None, False, False, False)
    )

    result = signals_for(session, ["00000006", None, "99999999"], api_key=None)

    assert result["00000006"].accounts_overdue is True
    assert "99999999" not in result  # not cached and no key -> skipped, no error
