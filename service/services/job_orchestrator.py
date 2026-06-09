"""
JobOrchestrator -- coordinates the full job creation lifecycle.

Pulls all dependencies from the :class:`~service.registry.ServiceRegistry`.
Handles:

1. Idempotency check (return existing job if key matches)
2. Business rule validation (via ValidationService)
3. Atomic overlap check + insert (via JobRepository)
4. MQTT dispatch (via MessageBroker)

This is the single entry point for job mutation logic, keeping
route handlers thin.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from http import HTTPStatus

from service import constants as C
from service.logger import get_logger
from service.models import JobCreate
from service.providers.broker import MessageBroker
from service.providers.repository import JobRepository
from service.registry import ServiceRegistry
from service.services.validation_service import JobValidationService

log = get_logger("orchestrator")


class JobOrchestrator:
    """Coordinates validation, persistence, and dispatch for job operations."""

    def __init__(self, registry: ServiceRegistry) -> None:
        self._repo: JobRepository = registry.resolve(JobRepository)
        self._broker: MessageBroker = registry.resolve(MessageBroker)
        self._validator: JobValidationService = registry.resolve(
            JobValidationService,
        )

    def create_job(
        self,
        body: JobCreate,
        user_id: str,
        idempotency_key: str,
    ) -> tuple[int, dict | str]:
        """Create a job.

        Returns ``(http_status, job_dict_or_error_message)``.
        """
        # Idempotent replay
        existing = self._repo.find_by_idempotency_key(user_id, idempotency_key)
        if existing:
            log.info(f"idempotent replay key={idempotency_key}")
            return HTTPStatus.CREATED, existing

        # Validation
        active_count = self._repo.count_active_jobs(user_id)
        error = self._validator.validate(body, user_id, active_count)
        if error:
            status, message = error
            return status, message

        # Build job dict
        now = datetime.now(timezone.utc).strftime(C.TIMESTAMP_FORMAT)
        job = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            C.FIELD_ASSET_ID: body.asset_id,
            C.FIELD_OPERATION: body.operation,
            C.FIELD_START_TIME: body.start_time.strftime(C.TIMESTAMP_FORMAT),
            C.FIELD_END_TIME: body.end_time.strftime(C.TIMESTAMP_FORMAT),
            C.FIELD_STATE: C.STATE_PENDING,
            C.FIELD_ERROR_MESSAGE: None,
            "idempotency_key": idempotency_key,
            "created_at": now,
            "updated_at": now,
        }

        # Atomic overlap check + insert
        outcome, result = self._repo.insert_if_no_overlap(job)
        if outcome == "overlap":
            return HTTPStatus.CONFLICT, C.ErrorMessages.OVERLAP_CONFLICT
        if outcome == "idempotent":
            log.info(f"concurrent idempotent replay key={idempotency_key}")
            return HTTPStatus.CREATED, result

        # Dispatch to worker
        self._broker.publish_dispatch(result)
        log.info(f"job created and dispatched id={result['id']}")
        return HTTPStatus.CREATED, result

    def get_job(self, job_id: str, user_id: str) -> dict | None:
        return self._repo.find_by_id(job_id, user_id)

    def list_jobs(self, user_id: str) -> list[dict]:
        return self._repo.list_by_user(user_id)
