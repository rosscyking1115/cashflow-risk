"""FastAPI application exposing the cashflow-risk engine to the dashboard.

Two analysis entry points: a zero-input ``/api/analyze/demo`` over synthetic
data, and ``/api/analyze`` which ingests an uploaded invoice CSV. Both return the
same :class:`AnalysisResponse` shape.

Note: this is the demo-data API surface. Auth, tenant isolation, and a DPIA come
before any real personal/financial data is processed (see
``docs/security_privacy.md``).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from cashflow_risk.analysis import analyze_invoices
from cashflow_risk.api.schemas import AnalysisResponse, IssueDTO
from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.ingestion.csv_import import parse_invoices_csv

app = FastAPI(title="Cashflow Risk Intelligence API", version="0.1.0")

# Dev only: the Next.js dashboard runs on :3000. Tighten for deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze/demo")
def analyze_demo() -> AnalysisResponse:
    ds = generate_dataset(GeneratorConfig(seed=1, n_customers=25))
    as_of = date(2025, 1, 1) + timedelta(weeks=30)
    analysis = analyze_invoices(
        ds.invoices,
        as_of=as_of,
        opening_balance=8000,
        minimum_reserve=6000,
        business_id=ds.business.id,
    )
    return AnalysisResponse.of(analysis)


@app.post("/api/analyze")
async def analyze_upload(
    invoices: Annotated[UploadFile, File()],
    opening_balance: Annotated[float, Form()] = 0.0,
    minimum_reserve: Annotated[float, Form()] = 0.0,
    business_id: Annotated[str, Form()] = "uploaded",
) -> AnalysisResponse:
    raw = (await invoices.read()).decode("utf-8-sig", errors="replace")
    parsed = parse_invoices_csv(raw, business_id=business_id)
    issues = [
        IssueDTO(row=i.row, message=i.message, field=i.field, severity=i.severity)
        for i in parsed.issues
    ]
    analysis = analyze_invoices(
        parsed.records,
        as_of=date.today(),
        opening_balance=opening_balance,
        minimum_reserve=minimum_reserve,
        business_id=business_id,
    )
    return AnalysisResponse.of(analysis, data_issues=issues)
