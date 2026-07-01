"""Error monitoring with PII scrubbing (DPIA R3; docs/security_privacy.md).

Sentry is initialised only when ``SENTRY_DSN`` is set, and is configured so that
personal and financial data can never reach it:

- ``send_default_pii=False`` — no user context, IPs, or cookies;
- ``include_local_variables=False`` — stack locals in this codebase carry invoice
  amounts, customer names, and whole uploaded CSVs; never capture them;
- ``max_request_body_size="never"`` — an upload body *is* the customer's ledger;
- ``before_send=scrub_event`` — defence in depth: strips any request body or
  cookie the SDK still attached, redacts auth headers, and recursively redacts
  every field whose key names something financial or identifying.

Stack traces (file names, functions, line numbers) survive scrubbing — errors
stay debuggable, data stays private.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast

import sentry_sdk

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

REDACTED = "[redacted]"

# A key is sensitive when any of its `_`/`-`-separated segments matches one of
# these. Segment matching keeps "filename"/"lineno" safe while catching
# "customer_name", "opening_balance", "company_number", "Authorization"...
_SENSITIVE_SEGMENTS = frozenset(
    {
        "amount",
        "amounts",
        "balance",
        "invoice",
        "invoices",
        "customer",
        "customers",
        "supplier",
        "email",
        "name",
        "csv",
        "token",
        "authorization",
        "cookie",
        "cookies",
        "secret",
        "password",
        "account",
        "company",
        "phone",
        "address",
    }
)


def _is_sensitive(key: str) -> bool:
    segments = key.lower().replace("-", "_").split("_")
    return any(segment in _SENSITIVE_SEGMENTS for segment in segments)


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: REDACTED if isinstance(k, str) and _is_sensitive(k) else _scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def scrub_event(event: Event, hint: Hint) -> Event | None:
    """Sentry ``before_send`` hook. Pure: returns a scrubbed copy of the event."""
    raw: dict[str, Any] = dict(event)
    request = raw.get("request")
    if isinstance(request, dict):
        request = dict(request)
        request.pop("data", None)  # an uploaded body is the customer's ledger
        request.pop("cookies", None)
        raw["request"] = request
    return cast("Event", _scrub(raw))


def init_sentry() -> bool:
    """Initialise Sentry iff ``SENTRY_DSN`` is set; returns whether it was.

    Call before the FastAPI app is created so the SDK's ASGI integration hooks
    request handling. Without a DSN this is a clean no-op (dev, tests, CI).
    """
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("CASHFLOW_ENV", "development"),
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=scrub_event,
    )
    return True
