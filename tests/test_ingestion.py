"""Behaviour of CSV ingestion for invoices and bank transactions.

Real uploads are messy: UK date formats, £ and thousands separators, missing or
mislabelled columns, duplicate rows, junk values. The parser must coerce what it
can, report per-row issues with clear messages, and never raise on bad input.
"""

import textwrap
from decimal import Decimal

from cashflow_risk.domain import TransactionDirection
from cashflow_risk.ingestion.csv_import import parse_invoices_csv, parse_transactions_csv


def test_parses_a_clean_invoice_csv() -> None:
    csv_text = textwrap.dedent(
        """\
        invoice_id,customer_id,amount,issue_date,due_date
        INV-1,C1,1000.00,2026-01-01,2026-01-31
        INV-2,C2,2500.50,2026-01-05,2026-02-04
        """
    )

    result = parse_invoices_csv(csv_text, business_id="biz")

    assert result.ok
    assert len(result.records) == 2
    assert result.records[0].amount == Decimal("1000.00")
    assert result.records[0].due_date.isoformat() == "2026-01-31"
    assert result.records[0].business_id == "biz"
    assert not result.issues


def test_handles_uk_dates_currency_symbols_and_aliased_headers() -> None:
    csv_text = textwrap.dedent(
        """\
        Invoice Number,Customer,Total,Issue Date,Due Date
        INV-9,Acme Ltd,"£1,234.56",05/02/2026,07/03/2026
        """
    )

    result = parse_invoices_csv(csv_text, business_id="biz")

    assert result.ok
    inv = result.records[0]
    assert inv.amount == Decimal("1234.56")
    assert inv.issue_date.isoformat() == "2026-02-05"  # day-first
    assert inv.customer_id == "Acme Ltd"


def test_missing_required_column_is_a_clear_file_level_error() -> None:
    csv_text = "invoice_id,customer_id,amount\nINV-1,C1,100\n"

    result = parse_invoices_csv(csv_text, business_id="biz")

    assert result.ok is False
    assert result.records == []
    assert "issue_date" in result.errors[0].message
    assert "due_date" in result.errors[0].message


def test_bad_row_is_reported_but_other_rows_still_parse() -> None:
    csv_text = textwrap.dedent(
        """\
        invoice_id,customer_id,amount,issue_date,due_date
        INV-1,C1,not-a-number,2026-01-01,2026-01-31
        INV-2,C2,2000,2026-01-05,2026-02-04
        """
    )

    result = parse_invoices_csv(csv_text, business_id="biz")

    assert len(result.records) == 1
    assert result.records[0].id == "INV-2"
    assert result.ok is False
    assert result.errors[0].row == 1


def test_duplicate_invoice_id_is_a_warning_and_first_wins() -> None:
    csv_text = textwrap.dedent(
        """\
        invoice_id,customer_id,amount,issue_date,due_date
        INV-1,C1,1000,2026-01-01,2026-01-31
        INV-1,C1,9999,2026-01-01,2026-01-31
        """
    )

    result = parse_invoices_csv(csv_text, business_id="biz")

    assert len(result.records) == 1
    assert result.records[0].amount == Decimal("1000")
    assert result.ok is True  # a duplicate is a warning, not an error
    assert result.warnings[0].field == "invoice_id"


def test_non_positive_amount_is_rejected_per_row() -> None:
    csv_text = textwrap.dedent(
        """\
        invoice_id,customer_id,amount,issue_date,due_date
        INV-1,C1,-50,2026-01-01,2026-01-31
        """
    )

    result = parse_invoices_csv(csv_text, business_id="biz")

    assert result.records == []
    assert result.errors[0].row == 1


def test_transactions_infer_direction_from_signed_amount() -> None:
    csv_text = textwrap.dedent(
        """\
        Date,Description,Amount
        01/03/2026,Client payment,1500.00
        03/03/2026,Office rent,-800.00
        """
    )

    result = parse_transactions_csv(csv_text, business_id="biz")

    assert result.ok
    assert result.records[0].direction is TransactionDirection.INFLOW
    assert result.records[0].amount == Decimal("1500.00")
    assert result.records[1].direction is TransactionDirection.OUTFLOW
    assert result.records[1].amount == Decimal("800.00")


def test_transactions_support_money_in_money_out_columns() -> None:
    csv_text = textwrap.dedent(
        """\
        Date,Details,Money In,Money Out
        01/03/2026,Invoice paid,2000.00,
        02/03/2026,Supplier,,350.00
        """
    )

    result = parse_transactions_csv(csv_text, business_id="biz")

    assert result.ok
    assert result.records[0].direction is TransactionDirection.INFLOW
    assert result.records[1].direction is TransactionDirection.OUTFLOW
    assert result.records[1].amount == Decimal("350.00")


def test_parses_optional_company_number() -> None:
    csv_text = textwrap.dedent(
        """\
        invoice_id,customer_id,amount,issue_date,due_date,company_number
        INV-1,Acme Ltd,1000,2026-01-01,2026-01-31,SYNTH-0001
        INV-2,Sole Trader,500,2026-01-01,2026-02-01,
        """
    )

    result = parse_invoices_csv(csv_text, business_id="biz")

    assert result.ok
    assert result.records[0].company_number == "SYNTH-0001"
    assert result.records[1].company_number is None


def test_transactions_without_any_amount_column_is_a_file_error() -> None:
    result = parse_transactions_csv("Date,Description\n01/03/2026,x\n", business_id="biz")

    assert result.ok is False
    assert "amount" in result.errors[0].message.lower()
