"""Hardening for invoice-file uploads (docs/security_privacy.md).

The limits protect the service; the content checks protect the user — a clear
"this is an Excel file, export it as CSV" beats a screen full of parse issues.

Browser-supplied MIME types are deliberately ignored (browsers send anything
from ``text/csv`` to ``application/vnd.ms-excel`` for the same file); the bytes
are what get checked. XLSX is not accepted on upload at all — that is also the
parser-bomb defence: there is no zip/XML parser on this path to bomb.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

# Generous for the segment: 5 MB / 50k rows is decades of invoices for a UK
# B2B service SME, and small enough that a hostile upload is boring.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50_000

_CHUNK = 64 * 1024
_ZIP_MAGIC = b"PK\x03\x04"  # every .xlsx is a zip


async def read_csv_upload(upload: UploadFile) -> str:
    """Read, validate, and decode an uploaded CSV; raise HTTPException otherwise.

    Enforces the byte limit *while* reading (never buffers an oversized body),
    then sniffs the content and applies the row limit before any parsing.
    """
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(_CHUNK):
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"File too large — the limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
                "If your ledger is bigger, split the export by year.",
            )
        chunks.append(chunk)
    raw = b"".join(chunks)

    if not raw.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The uploaded file is empty.")
    if raw.startswith(_ZIP_MAGIC):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "This looks like an Excel (.xlsx) file. Please export it as CSV and upload that.",
        )
    if b"\x00" in raw[:8192]:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "This doesn't look like a text CSV file. Please upload a CSV export.",
        )

    text = raw.decode("utf-8-sig", errors="replace")
    if text.count("\n") > MAX_ROWS:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Too many rows — the limit is {MAX_ROWS:,}. Split the export and upload in parts.",
        )
    return text
