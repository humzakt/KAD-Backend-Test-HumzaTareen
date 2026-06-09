"""
FastAPI route definitions.

Thin handlers that delegate business logic to the
:class:`~service.services.job_orchestrator.JobOrchestrator`.
Each route validates HTTP-level concerns (headers, status codes)
and lets the service layer handle domain rules.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from service import constants as C
from service.api.dependencies import get_current_user, get_registry
from service.models import JobCreate
from service.services.job_orchestrator import JobOrchestrator

health_router = APIRouter()
api_router = APIRouter(prefix="/api")


@health_router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@api_router.get("/jobs")
def list_jobs(user: dict = Depends(get_current_user)) -> list[dict]:
    orchestrator: JobOrchestrator = get_registry().resolve(JobOrchestrator)
    return orchestrator.list_jobs(user["user_id"])


@api_router.get("/jobs/{job_id}")
def get_job(
    job_id: str, user: dict = Depends(get_current_user),
) -> dict:
    orchestrator: JobOrchestrator = get_registry().resolve(JobOrchestrator)
    job = orchestrator.get_job(job_id, user["user_id"])
    if not job:
        raise HTTPException(
            status_code=C.HTTP_NOT_FOUND,
            detail=C.ErrorMessages.JOB_NOT_FOUND,
        )
    return job


@api_router.post("/jobs", status_code=C.HTTP_CREATED)
def create_job(
    body: JobCreate,
    user: dict = Depends(get_current_user),
    idempotency_key: str = Header(None, alias=C.HEADER_IDEMPOTENCY_KEY),
) -> dict:
    # 400: Idempotency-Key validation (HTTP-level, not business rule)
    if not idempotency_key or len(idempotency_key.strip()) == 0:
        raise HTTPException(
            status_code=C.HTTP_BAD_REQUEST,
            detail=C.ErrorMessages.IDEMPOTENCY_KEY_REQUIRED,
        )
    if len(idempotency_key) > C.IDEMPOTENCY_KEY_MAX_LENGTH:
        raise HTTPException(
            status_code=C.HTTP_BAD_REQUEST,
            detail=C.ErrorMessages.IDEMPOTENCY_KEY_TOO_LONG,
        )

    orchestrator: JobOrchestrator = get_registry().resolve(JobOrchestrator)
    status, result = orchestrator.create_job(
        body, user["user_id"], idempotency_key,
    )

    if isinstance(result, str):
        raise HTTPException(status_code=status, detail=result)
    return result
