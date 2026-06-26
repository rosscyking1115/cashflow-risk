"""CSV import for invoices and bank transactions.

Parses messy real-world exports into validated domain entities. The parser is
forgiving about *form* (column aliases, UK date formats, ``£``/thousands
separators) and strict about *meaning* (required columns, positive amounts,
valid dates). It never raises on bad input: every problem becomes a
:class:`RowIssue` so the UI can show clear, row-level feedback.

CSV only for now; XLSX support (via openpyxl) slots in behind the same
``ImportResult`` interface later.
"""

from __future__ import annotations

import csv as _csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from cashflow_risk.domain import Invoice, InvoiceStatus, Transaction, TransactionDirection

MAX_ROWS = 100_000

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y")

_INVOICE_ALIASES: dict[str, set[str]] = {
    "invoice_id": {"invoice_id", "id", "invoice", "invoice number", "number", "ref"},
    "customer_id": {"customer_id", "customer", "client", "customer name", "account"},
    "amount": {"amount", "total", "gross", "value", "amount due"},
    "issue_date": {"issue_date", "issued", "date", "invoice date"},
    "due_date": {"due_date", "due", "payment due", "due date"},
    "paid_date": {"paid_date", "paid", "date paid", "payment date"},
    "status": {"status"},
}
_INVOICE_REQUIRED = {"invoice_id", "customer_id", "amount", "issue_date", "due_date"}

_TXN_ALIASES: dict[str, set[str]] = {
    "date": {"date", "transaction date", "posted", "posting date"},
    "amount": {"amount", "value"},
    "money_in": {"money_in", "money in", "paid_in", "paid in", "credit"},
    "money_out": {"money_out", "money out", "paid_out", "paid out", "debit"},
    "description": {"description", "details", "narrative", "reference", "memo"},
    "direction": {"direction", "type"},
}


@dataclass(frozen=True)
class RowIssue:
    """A single problem found while importing, with enough context to fix it."""

    row: int  # 1-based data row; 0 means a file-level (header) issue
    message: str
    field: str | None = None
    severity: str = "error"  # "error" | "warning"


@dataclass
class ImportResult[T]:
    """Parsed records plus every issue encountered."""

    records: list[T] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[RowIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[RowIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        """True when nothing failed outright (warnings are allowed)."""
        return not self.errors


def _norm(name: str) -> str:
    """Normalise a header for matching: lowercase, no spaces or underscores."""
    return "".join(name.lower().split()).replace("_", "")


def _resolve_columns(fieldnames: Iterable[str], aliases: Mapping[str, set[str]]) -> dict[str, str]:
    """Map canonical field -> the actual header present (case/space/_-insensitive)."""
    present = {_norm(name): name for name in fieldnames}
    resolved: dict[str, str] = {}
    for canonical, names in aliases.items():
        for candidate in names:
            if _norm(candidate) in present:
                resolved[canonical] = present[_norm(candidate)]
                break
    return resolved


def _parse_money(raw: str) -> Decimal:
    s = raw.strip().replace("£", "").replace(",", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):  # accounting negatives: (1,200)
        s = "-" + s[1:-1]
    if not s:
        raise InvalidOperation("empty amount")
    return Decimal(s)


def _parse_date(raw: str) -> date:
    s = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    from dateutil import parser as _dtp  # lazy: only on fallback

    return _dtp.parse(s, dayfirst=True).date()


def parse_invoices_csv(
    text: str, *, business_id: str, max_rows: int = MAX_ROWS
) -> ImportResult[Invoice]:
    result: ImportResult[Invoice] = ImportResult()
    reader = _csv.DictReader(io.StringIO(text))
    cols = _resolve_columns(reader.fieldnames or [], _INVOICE_ALIASES)

    missing = _INVOICE_REQUIRED - cols.keys()
    if missing:
        result.issues.append(
            RowIssue(0, f"Missing required column(s): {', '.join(sorted(missing))}")
        )
        return result

    seen: set[str] = set()
    for n, raw in enumerate(reader, start=1):
        if n > max_rows:
            result.issues.append(RowIssue(n, f"Row limit {max_rows} exceeded; rest ignored"))
            break
        try:
            amount = _parse_money(raw[cols["amount"]])
            issue_date = _parse_date(raw[cols["issue_date"]])
            due_date = _parse_date(raw[cols["due_date"]])
        except (InvalidOperation, ValueError) as exc:
            result.issues.append(RowIssue(n, f"Could not parse row: {exc}"))
            continue

        invoice_id = raw[cols["invoice_id"]].strip()
        if invoice_id in seen:
            result.issues.append(
                RowIssue(
                    n,
                    f"Duplicate invoice id {invoice_id!r}; kept first",
                    "invoice_id",
                    "warning",
                )
            )
            continue

        paid_raw = raw.get(cols.get("paid_date", ""), "").strip()
        paid_date: date | None = None
        if paid_raw:
            try:
                paid_date = _parse_date(paid_raw)
            except ValueError:
                result.issues.append(
                    RowIssue(
                        n,
                        f"Unparseable paid_date {paid_raw!r}; treated as unpaid",
                        "paid_date",
                        "warning",
                    )
                )

        status = InvoiceStatus.PAID if paid_date else InvoiceStatus.OPEN
        try:
            invoice = Invoice(
                id=invoice_id,
                business_id=business_id,
                customer_id=raw[cols["customer_id"]].strip(),
                amount=amount,
                issue_date=issue_date,
                due_date=due_date,
                paid_date=paid_date,
                amount_paid=amount if paid_date else Decimal("0"),
                status=status,
            )
        except ValidationError as exc:
            result.issues.append(RowIssue(n, _first_error(exc)))
            continue

        seen.add(invoice_id)
        result.records.append(invoice)

    return result


def parse_transactions_csv(
    text: str, *, business_id: str, account_id: str = "imported", max_rows: int = MAX_ROWS
) -> ImportResult[Transaction]:
    result: ImportResult[Transaction] = ImportResult()
    reader = _csv.DictReader(io.StringIO(text))
    cols = _resolve_columns(reader.fieldnames or [], _TXN_ALIASES)

    if "date" not in cols:
        result.issues.append(RowIssue(0, "Missing required column(s): date"))
        return result
    has_amount = "amount" in cols
    has_split = "money_in" in cols or "money_out" in cols
    if not (has_amount or has_split):
        result.issues.append(
            RowIssue(0, "Need an 'amount' column or 'money_in'/'money_out' columns")
        )
        return result

    for n, raw in enumerate(reader, start=1):
        if n > max_rows:
            result.issues.append(RowIssue(n, f"Row limit {max_rows} exceeded; rest ignored"))
            break
        try:
            txn_date = _parse_date(raw[cols["date"]])
            signed = _signed_amount(raw, cols, has_amount)
        except (InvalidOperation, ValueError) as exc:
            result.issues.append(RowIssue(n, f"Could not parse row: {exc}"))
            continue

        if signed == 0:
            result.issues.append(RowIssue(n, "Zero-value transaction skipped", severity="warning"))
            continue

        direction = TransactionDirection.INFLOW if signed > 0 else TransactionDirection.OUTFLOW
        description = raw.get(cols.get("description", ""), "").strip()
        try:
            txn = Transaction(
                id=f"txn_{n}",
                business_id=business_id,
                account_id=account_id,
                date=txn_date,
                amount=abs(signed),
                direction=direction,
                description=description,
            )
        except ValidationError as exc:
            result.issues.append(RowIssue(n, _first_error(exc)))
            continue
        result.records.append(txn)

    return result


def _signed_amount(raw: Mapping[str, str], cols: Mapping[str, str], has_amount: bool) -> Decimal:
    if has_amount:
        return _parse_money(raw[cols["amount"]])
    money_in = raw.get(cols.get("money_in", ""), "").strip()
    money_out = raw.get(cols.get("money_out", ""), "").strip()
    if money_in:
        return _parse_money(money_in)
    if money_out:
        return -_parse_money(money_out)
    raise InvalidOperation("no amount in row")


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(p) for p in err.get("loc", ()))
    return f"{loc}: {err.get('msg', 'invalid value')}"
