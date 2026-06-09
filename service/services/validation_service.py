"""
JobValidationService -- business rule validation for job submissions.

Enforces all rules from PDF section 4.4:

- ``asset_id`` must exist in seed data
- ``start_time`` must be in the future
- ``start_time < end_time``
- Duration between 15 minutes and 4 hours
- ``operation`` is non-empty, max 64 chars
- User may have at most 10 active jobs

Returns ``(status_code, message)`` on failure, ``None`` on success.
This separation keeps validation logic testable independently of HTTP.
"""
from __future__ import annotations

from datetime import datetime, timezone

from service import config
from service import constants as C
from service.logger import get_logger
from service.models import JobCreate

log = get_logger("validation")


class JobValidationService:
    """Stateless validator for job creation requests."""

    def validate(
        self,
        body: JobCreate,
        user_id: str,
        active_count: int,
    ) -> tuple[int, str] | None:
        """Validate a job creation request.

        Returns ``(http_status, message)`` on failure, ``None`` if valid.
        """
        if body.asset_id not in config.VALID_ASSETS:
            return (
                C.HTTP_UNPROCESSABLE,
                C.ErrorMessages.UNKNOWN_ASSET.format(asset_id=body.asset_id),
            )

        if body.start_time <= datetime.now(timezone.utc):
            return C.HTTP_UNPROCESSABLE, C.ErrorMessages.START_TIME_IN_PAST

        if body.start_time >= body.end_time:
            return C.HTTP_UNPROCESSABLE, C.ErrorMessages.START_NOT_BEFORE_END

        duration = body.end_time - body.start_time
        if duration < C.MIN_JOB_DURATION:
            return C.HTTP_UNPROCESSABLE, C.ErrorMessages.DURATION_TOO_SHORT
        if duration > C.MAX_JOB_DURATION:
            return C.HTTP_UNPROCESSABLE, C.ErrorMessages.DURATION_TOO_LONG

        if not body.operation or len(body.operation) > C.OPERATION_MAX_LENGTH:
            return C.HTTP_UNPROCESSABLE, C.ErrorMessages.OPERATION_INVALID

        if active_count >= C.MAX_ACTIVE_JOBS_PER_USER:
            return C.HTTP_UNPROCESSABLE, C.ErrorMessages.MAX_ACTIVE_JOBS

        return None
