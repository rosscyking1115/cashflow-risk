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
from cashflow_risk.api.schemas import (
    AddMemberRequest,
    AnalysisResponse,
    AuditEventDTO,
    BusinessMembershipDTO,
    InvitationDTO,
    InvitationRequest,
    IssueDTO,
    RenameBusinessRequest,
    RunSummary,
)
from cashflow_risk.api.upload_guard import read_csv_upload
from cashflow_risk.auth import Principal, mint_token, require_principal
from cashflow_risk.auth.principal import OWNER, ROLES
from cashflow_risk.auth.settings import (
    dev_token_enabled,
    is_production,
    jwt_secret,
    using_default_secret,
)
from cashflow_risk.datagen.generator import GeneratorConfig, generate_dataset
from cashflow_risk.db import get_session, init_db
from cashflow_risk.db import repository as repo
from cashflow_risk.enrichment.service import companies_house_api_key, signals_for
from cashflow_risk.ingestion.csv_import import parse_invoices_csv
from cashflow_risk.observability import init_sentry

# Before the app object exists, so the SDK's ASGI integration wraps it. A clean
# no-op without SENTRY_DSN (dev/tests/CI). PII scrubbing: see observability.py.
init_sentry()


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
    if principal.role != OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read-only access: only an owner can upload")
    raw = await read_csv_upload(invoices)  # size/row limits + content sniffing
    parsed = parse_invoices_csv(raw, business_id=principal.business_id)
    issues = [
        IssueDTO(row=i.row, message=i.message, field=i.field, severity=i.severity)
        for i in parsed.issues
    ]
    numbers = [inv.company_number for inv in parsed.records if inv.company_number]
    signals = signals_for(session, numbers, api_key=companies_house_api_key())
    analysis = analyze_invoices(
        parsed.records,
        as_of=date.today(),
        opening_balance=opening_balance,
        minimum_reserve=minimum_reserve,
        business_id=principal.business_id,  # tenant from token, never client input
        company_signals=signals,
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
    repo.record_audit_event(
        session,
        business_id=principal.business_id,
        actor_user_id=principal.user_id,
        action="run.create",
        detail={"run_id": response.run_id, "rows": len(parsed.records), "issues": len(issues)},
    )
    return response


def _is_owner(session: Session, *, user_id: str, business_id: str) -> bool:
    if business_id == user_id:  # a user always owns their own business
        return True
    membership = repo.get_membership(session, user_id=user_id, business_id=business_id)
    return membership is not None and membership.role == OWNER


def _business_name(session: Session, business_id: str) -> str | None:
    business = repo.get_business(session, business_id)
    return business.name if business else None


@app.get("/api/businesses")
def list_businesses(principal: PrincipalDep, session: SessionDep) -> list[BusinessMembershipDTO]:
    if principal.email:
        # accept any invitations sent to this user's email
        repo.claim_invitations(session, user_id=principal.user_id, email=principal.email.lower())
    own = BusinessMembershipDTO(
        business_id=principal.user_id,
        role=OWNER,
        name=_business_name(session, principal.user_id),
    )
    granted = [
        BusinessMembershipDTO(
            business_id=m.business_id, role=m.role, name=_business_name(session, m.business_id)
        )
        for m in repo.list_memberships(session, user_id=principal.user_id)
    ]
    return [own, *granted]


@app.put("/api/businesses/{business_id}")
def rename_business(
    business_id: str,
    req: RenameBusinessRequest,
    principal: PrincipalDep,
    session: SessionDep,
) -> BusinessMembershipDTO:
    if not _is_owner(session, user_id=principal.user_id, business_id=business_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the business owner can rename it")
    business = repo.set_business_name(session, business_id=business_id, name=req.name.strip())
    repo.record_audit_event(
        session,
        business_id=business_id,
        actor_user_id=principal.user_id,
        action="business.rename",
    )
    return BusinessMembershipDTO(business_id=business_id, role=OWNER, name=business.name)


@app.post("/api/businesses/{business_id}/members")
def add_member(
    business_id: str,
    req: AddMemberRequest,
    principal: PrincipalDep,
    session: SessionDep,
) -> BusinessMembershipDTO:
    if not _is_owner(session, user_id=principal.user_id, business_id=business_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the business owner can add members")
    if req.role not in ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"role must be one of {sorted(ROLES)}"
        )
    membership = repo.add_membership(
        session, user_id=req.user_id, business_id=business_id, role=req.role
    )
    repo.record_audit_event(
        session,
        business_id=business_id,
        actor_user_id=principal.user_id,
        action="member.add",
        detail={"role": req.role},
    )
    return BusinessMembershipDTO(business_id=membership.business_id, role=membership.role)


@app.post("/api/businesses/{business_id}/invitations")
def invite_member(
    business_id: str,
    req: InvitationRequest,
    principal: PrincipalDep,
    session: SessionDep,
) -> InvitationDTO:
    if not _is_owner(session, user_id=principal.user_id, business_id=business_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the business owner can invite")
    if req.role not in ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"role must be one of {sorted(ROLES)}"
        )
    invitation = repo.create_invitation(
        session, email=req.email.strip().lower(), business_id=business_id, role=req.role
    )
    repo.record_audit_event(
        session,
        business_id=business_id,
        actor_user_id=principal.user_id,
        action="member.invite",
        detail={"role": req.role},  # deliberately no email in the trail
    )
    return InvitationDTO(email=invitation.email, role=invitation.role)


@app.get("/api/businesses/{business_id}/invitations")
def list_invitations(
    business_id: str, principal: PrincipalDep, session: SessionDep
) -> list[InvitationDTO]:
    if not _is_owner(session, user_id=principal.user_id, business_id=business_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the business owner can view invitations"
        )
    return [
        InvitationDTO(email=i.email, role=i.role)
        for i in repo.list_invitations(session, business_id=business_id)
    ]


@app.get("/api/account/export")
def export_account(principal: PrincipalDep, session: SessionDep) -> JSONResponse:
    """Everything we hold for the signed-in user, as a JSON download (DPIA R6:
    access/portability). Keyed to the *user*, never the switched business."""
    export = repo.export_account(session, user_id=principal.user_id, email=principal.email)
    repo.record_audit_event(
        session,
        business_id=principal.user_id,  # the export is of their own business
        actor_user_id=principal.user_id,
        action="account.export",
    )
    return JSONResponse(
        content=export,
        headers={"Content-Disposition": 'attachment; filename="cashflow-account-export.json"'},
    )


@app.delete("/api/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(principal: PrincipalDep, session: SessionDep) -> Response:
    """Erase everything we hold for the signed-in user (DPIA R6: erasure).
    Keyed to the *user*; an accountant deleting their account never touches a
    client's business. Their IdP (Clerk) account is deleted separately."""
    repo.delete_account(session, user_id=principal.user_id, email=principal.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/audit")
def list_audit(principal: PrincipalDep, session: SessionDep) -> list[AuditEventDTO]:
    """The active business's audit trail. Anyone with access to the business may
    read it (owners and invited accountants alike) — that visibility is the point."""
    return [
        AuditEventDTO(
            action=e.action,
            actor_user_id=e.actor_user_id,
            created_at=e.created_at,
            detail=e.detail,
        )
        for e in repo.list_audit_events(session, business_id=principal.business_id)
    ]


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
    repo.record_audit_event(
        session,
        business_id=principal.business_id,
        actor_user_id=principal.user_id,
        action="run.export",
        detail={"run_id": run_id},
    )
    return Response(
        content=workbook,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="cashflow-{run_id}.xlsx"'},
    )
