"""Daily Companies House refresh worker — re-fetches every cached company's
signals and upserts them, so filing/insolvency changes flow into the risk score.
Tested against a mocked httpx client; no network."""

from datetime import date

import httpx

from cashflow_risk.datagen.generator import synthetic_company_number
from cashflow_risk.db import get_session
from cashflow_risk.db import repository as repo
from cashflow_risk.enrichment.companies_house import BASE_URL, CompanySignals
from cashflow_risk.enrichment.refresh import RefreshResult, refresh_all_signals

# Non-resolvable identifiers. These fixtures assert overdue filings and
# insolvency, which must never be attached to a real company number.
CACHED = synthetic_company_number(6)
OTHER = synthetic_company_number(7)
OK, GONE, ERRORING = (synthetic_company_number(i) for i in (1, 2, 3))

STALE = CompanySignals(CACHED, "active", False, None, False, False, False)
FRESH_PROFILE = {
    "company_status": "active",
    "accounts": {"next_accounts": {"due_on": "2026-09-30", "overdue": True}},
    "confirmation_statement": {"overdue": False},
    "links": {"insolvency": f"/company/{CACHED}/insolvency"},
}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL, auth=("k", ""))


def _overdue(number: str) -> CompanySignals:
    return CompanySignals(number, "active", True, None, False, False, False)


def test_all_company_numbers_lists_every_cached_company() -> None:
    session = next(get_session())
    repo.upsert_company_signals(session, STALE)
    repo.upsert_company_signals(session, _overdue(OTHER))

    assert set(repo.all_company_numbers(session)) == {CACHED, OTHER}


def test_refresh_re_fetches_and_upserts_changed_signals() -> None:
    session = next(get_session())
    repo.upsert_company_signals(session, STALE)  # cache says: clean

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=FRESH_PROFILE)

    result = refresh_all_signals(session, api_key="k", client=_client(handler))

    assert result == RefreshResult(total=1, refreshed=1, not_found=0, errors=0)
    updated = repo.get_company_signals(session, CACHED)
    assert updated is not None
    assert updated.accounts_overdue is True  # picked up the new filing state
    assert updated.has_insolvency is True
    assert updated.accounts_next_due == date(2026, 9, 30)


def test_refresh_is_resilient_to_404_and_errors() -> None:
    session = next(get_session())
    repo.upsert_company_signals(session, _overdue(OK))
    repo.upsert_company_signals(session, _overdue(GONE))
    repo.upsert_company_signals(session, _overdue(ERRORING))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/company/{GONE}":
            return httpx.Response(404)
        if request.url.path == f"/company/{ERRORING}":
            return httpx.Response(500)
        return httpx.Response(200, json={"company_status": "active"})

    result = refresh_all_signals(session, api_key="k", client=_client(handler))

    assert result.total == 3
    assert result.refreshed == 1  # only OK succeeded
    assert result.not_found == 1  # GONE is no longer on the register
    assert result.errors == 1  # ERRORING raised, but the batch continued
    # a failed fetch leaves the previously cached signals untouched
    stale = repo.get_company_signals(session, ERRORING)
    assert stale is not None and stale.accounts_overdue is True


def test_refresh_empty_cache_is_a_no_op() -> None:
    session = next(get_session())

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        raise AssertionError("should not fetch when nothing is cached")

    result = refresh_all_signals(session, api_key="k", client=_client(handler))

    assert result == RefreshResult(total=0, refreshed=0, not_found=0, errors=0)
