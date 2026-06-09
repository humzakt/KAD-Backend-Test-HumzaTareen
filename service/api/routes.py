"""
FastAPI route definitions.

Thin handlers that delegate business logic to the
:class:`~service.services.job_orchestrator.JobOrchestrator`.
Each route validates HTTP-level concerns (headers, status codes)
and lets the service layer handle domain rules.
"""
from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, Depends, Header, HTTPException

from service import constants as C
from service.api.dependencies import get_current_user, get_registry
from service.models import JobCreate, JobResponse
from service.providers.broker import MessageBroker
from service.services.job_orchestrator import JobOrchestrator

health_router = APIRouter()
api_router = APIRouter(prefix="/api")


@health_router.get("/health")
def health() -> dict:
    broker: MessageBroker = get_registry().resolve(MessageBroker)
    return {"status": "ok", "mqtt_connected": broker.is_connected()}


@api_router.get("/jobs", response_model=list[JobResponse])
def list_jobs(user: dict = Depends(get_current_user)):
    orchestrator: JobOrchestrator = get_registry().resolve(JobOrchestrator)
    return orchestrator.list_jobs(user["user_id"])


@api_router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str, user: dict = Depends(get_current_user),
):
    orchestrator: JobOrchestrator = get_registry().resolve(JobOrchestrator)
    job = orchestrator.get_job(job_id, user["user_id"])
    if not job:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=C.ErrorMessages.JOB_NOT_FOUND,
        )
    return job


@api_router.post("/jobs", status_code=HTTPStatus.CREATED, response_model=JobResponse)
def create_job(
    body: JobCreate,
    user: dict = Depends(get_current_user),
    idempotency_key: str = Header(None, alias=C.HEADER_IDEMPOTENCY_KEY),
):
    # 400: Idempotency-Key validation (HTTP-level, not business rule)
    if not idempotency_key or len(idempotency_key.strip()) == 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=C.ErrorMessages.IDEMPOTENCY_KEY_REQUIRED,
        )
    if len(idempotency_key) > C.IDEMPOTENCY_KEY_MAX_LENGTH:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=C.ErrorMessages.IDEMPOTENCY_KEY_TOO_LONG,
        )

    orchestrator: JobOrchestrator = get_registry().resolve(JobOrchestrator)
    status, result = orchestrator.create_job(
        body, user["user_id"], idempotency_key,
    )

    if isinstance(result, str):
        raise HTTPException(status_code=status, detail=result)
    return result
