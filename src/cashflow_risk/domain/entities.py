"""Canonical input entities — the system-of-record data the tool reasons over.

These are the source-of-record entities defined in ``CONTEXT.md``. Produced
artifacts (Forecast run, Risk signal, Action brief) live with the modules that
create them, not here.

Money is modelled as :class:`~decimal.Decimal` for exactness. Analytics layers
may convert to float internally, but the record of an Invoice or Transaction
amount is never a float.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, NonNegativeInt


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TransactionDirection(StrEnum):
    """Whether a Transaction moves money into or out of an Account."""

    INFLOW = "inflow"
    OUTFLOW = "outflow"


class InvoiceStatus(StrEnum):
    """Settlement state of an Invoice or Bill."""

    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    WRITTEN_OFF = "written_off"


class ObligationType(StrEnum):
    """Kind of scheduled HMRC payment (a Tax obligation)."""

    VAT = "vat"
    PAYE = "paye"
    CORPORATION_TAX = "corporation_tax"
    OTHER = "other"


class Business(BaseModel):
    """The UK SME that owns the data — the unit of tenancy."""

    id: str
    name: str
    sector: str | None = None
    country: str = "GB"
    created_at: datetime = Field(default_factory=_utcnow)


class Account(BaseModel):
    """A bank account held by a Business, with an opening balance."""

    id: str
    business_id: str
    name: str
    opening_balance: Decimal = Decimal("0")
    currency: str = "GBP"


class Customer(BaseModel):
    """A party the Business sends Invoices to."""

    id: str
    business_id: str
    name: str
    payment_terms_days: NonNegativeInt = 30


class Supplier(BaseModel):
    """A party that sends the Business Bills."""

    id: str
    business_id: str
    name: str


class Invoice(BaseModel):
    """Money owed *to* the Business by a Customer — a receivable.

    ``paid_date`` and the resulting overdue duration are *outcomes*. They are
    legitimate for ageing display but must never be used as prediction features
    (see ``docs/adr/0002-anti-circular-synthetic-data.md``).
    """

    id: str
    business_id: str
    customer_id: str
    amount: Decimal = Field(gt=0)
    issue_date: date
    due_date: date
    paid_date: date | None = None
    amount_paid: Decimal = Decimal("0")
    status: InvoiceStatus = InvoiceStatus.OPEN

    @property
    def outstanding(self) -> Decimal:
        """Amount still unpaid."""
        return self.amount - self.amount_paid

    @property
    def is_settled(self) -> bool:
        return self.status in (InvoiceStatus.PAID, InvoiceStatus.WRITTEN_OFF)

    def days_overdue(self, as_of: date) -> int:
        """Ageing relative to the due date at ``as_of``. Outcome, not a feature."""
        reference = min(self.paid_date, as_of) if self.paid_date is not None else as_of
        return max(0, (reference - self.due_date).days)


class Bill(BaseModel):
    """Money the Business owes *to* a Supplier — a payable."""

    id: str
    business_id: str
    supplier_id: str
    amount: Decimal = Field(gt=0)
    issue_date: date
    due_date: date
    paid_date: date | None = None
    status: InvoiceStatus = InvoiceStatus.OPEN

    @property
    def is_settled(self) -> bool:
        return self.status in (InvoiceStatus.PAID, InvoiceStatus.WRITTEN_OFF)


class TaxObligation(BaseModel):
    """A scheduled HMRC payment with a known due date — a deterministic outflow."""

    id: str
    business_id: str
    type: ObligationType
    amount: Decimal = Field(gt=0)
    due_date: date


class Transaction(BaseModel):
    """A single dated money movement on an Account that has already happened."""

    id: str
    business_id: str
    account_id: str
    date: date
    amount: Decimal = Field(gt=0)
    direction: TransactionDirection
    description: str = ""
    counterparty_id: str | None = None
