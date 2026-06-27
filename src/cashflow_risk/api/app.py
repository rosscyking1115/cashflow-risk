"""FastAPI application exposing the cashflow-risk engine to the dashboard.

Two analysis entry points: a zero-input ``/api/analyze/demo`` over synthetic data
(public — no real data, useful for marketing and user interviews), and
``/api/analyze`` which ingests an uploaded invoice CSV (**authenticated**; the
tenant is taken from the token, never from client input).

Auth is a provider-agnostic JWT seam (see ``cashflow_risk.auth``). A hosted IdP
slots into token verification before launch. A DPIA precedes the first real
upload (see ``docs/security_privacy.md``).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cashflow_risk.analysis import analyze_invoices
from cashflow_risk.api.schemas import AnalysisResponse, IssueDTO
from cashflow_risk.auth import Principal, mint_token, require_principal
from cashflow_risk.auth.settings import dev_token_enabled, jwt_secret
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


class DevTokenRequest(BaseModel):
    email: str
    business_id: str


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/dev-token")
def dev_token(req: DevTokenRequest) -> dict[str, str]:
    """Mint a local token for development. Disabled unless explicitly enabled."""
    if not dev_token_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    principal = Principal(user_id=req.email, business_id=req.business_id, email=req.email)
    return {"access_token": mint_token(principal, secret=jwt_secret()), "token_type": "bearer"}


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
    principal: Annotated[Principal, Depends(require_principal)],
    invoices: Annotated[UploadFile, File()],
    opening_balance: Annotated[float, Form()] = 0.0,
    minimum_reserve: Annotated[float, Form()] = 0.0,
) -> AnalysisResponse:
    raw = (await invoices.read()).decode("utf-8-sig", errors="replace")
    parsed = parse_invoices_csv(raw, business_id=principal.business_id)
    issues = [
        IssueDTO(row=i.row, message=i.message, field=i.field, severity=i.severity)
        for i in parsed.issues
    ]
    analysis = analyze_invoices(
        parsed.records,
        as_of=date.today(),
        opening_balance=opening_balance,
        minimum_reserve=minimum_reserve,
        business_id=principal.business_id,  # tenant from token, never client input
    )
    return AnalysisResponse.of(analysis, data_issues=issues)
