"""FastAPI application exposing the cashflow-risk engine to the dashboard.

Two analysis entry points: a zero-input ``/api/analyze/demo`` over synthetic data
(public — no real data, useful for marketing and user interviews), and
``/api/analyze`` which ingests an uploaded invoice CSV (**authenticated**; the
tenant is taken from the token, never from client input). Authenticated analyses
are persisted and retrievable via the tenant-scoped ``/api/runs`` endpoints.

Auth is a provider-agnostic JWT seam (see ``cashflow_risk.auth``). A hosted IdP
slots into token verification before launch. A DPIA precedes the first real
upload (see ``docs/security_privacy.md``).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cashflow_risk.analysis import analyze_invoices
from cashflow_risk.api.export import analysis_to_xlsx
from cashflow_risk.api.schemas import AnalysisResponse, IssueDTO, RunSummary
from cashflow_risk.auth import Principal, mint_token, require_principal
from cashflow_risk.auth.settings import (
    dev_token_enabled,
    is_production,
    jwt_secret,
    using_default_secret,
)
from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.db import get_session, init_db
from cashflow_risk.db import repository as repo
from cashflow_risk.ingestion.csv_import import parse_invoices_csv


def _allowed_origins() -> list[str]:
    """Dashboard origins permitted by CORS. Set CASHFLOW_ALLOWED_ORIGINS (comma-
    separated) in production; defaults to the local dev server."""
    raw = os.environ.get("CASHFLOW_ALLOWED_ORIGINS")
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def _allowed_origin_regex() -> str | None:
    """Optional regex of permitted origins (e.g. a platform's wildcard domain)."""
    return os.environ.get("CASHFLOW_ALLOWED_ORIGIN_REGEX")


logger = logging.getLogger("cashflow_risk.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if is_production() and using_default_secret():
        raise RuntimeError(
            "Refusing to start: set CASHFLOW_JWT_SECRET in production "
            "(the default dev secret is insecure)."
        )
    init_db()
    yield


app = FastAPI(title="Cashflow Risk Intelligence API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_origin_regex=_allowed_origin_regex(),
    allow_methods=["*"],
    allow_headers=["*"],
)

def _origin_allowed(origin: str) -> bool:
    if origin in _allowed_origins():
        return True
    regex = _allowed_origin_regex()
    return bool(regex and re.fullmatch(regex, origin))


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Return 500s *with* CORS headers so the browser shows a real error instead of
    an opaque 'Failed to fetch' (Starlette's error middleware sits outside CORS)."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    origin = request.headers.get("origin")
    if origin and _origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
    return response


SessionDep = Annotated[Session, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(require_principal)]


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
    principal: PrincipalDep,
    session: SessionDep,
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
    response = AnalysisResponse.of(analysis, data_issues=issues)
    response.run_id = uuid4().hex
    repo.save_run(
        session,
        run_id=response.run_id,
        business_id=principal.business_id,
        as_of=response.as_of,
        runway_weeks=response.brief.runway_weeks,
        has_shortfall=response.brief.has_shortfall,
        minimum_reserve=response.minimum_reserve,
        payload=response.model_dump(mode="json"),
    )
    return response


@app.get("/api/runs")
def list_runs(principal: PrincipalDep, session: SessionDep) -> list[RunSummary]:
    rows = repo.list_runs(session, business_id=principal.business_id)
    return [
        RunSummary(
            id=r.id,
            as_of=r.as_of,
            runway_weeks=r.runway_weeks,
            has_shortfall=r.has_shortfall,
            created_at=r.created_at,
        )
        for r in rows
    ]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, principal: PrincipalDep, session: SessionDep) -> AnalysisResponse:
    row = repo.get_run(session, business_id=principal.business_id, run_id=run_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return AnalysisResponse.model_validate(row.payload)


_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@app.get("/api/runs/{run_id}/export.xlsx")
def export_run(run_id: str, principal: PrincipalDep, session: SessionDep) -> Response:
    row = repo.get_run(session, business_id=principal.business_id, run_id=run_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    workbook = analysis_to_xlsx(AnalysisResponse.model_validate(row.payload))
    return Response(
        content=workbook,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="cashflow-{run_id}.xlsx"'},
    )
