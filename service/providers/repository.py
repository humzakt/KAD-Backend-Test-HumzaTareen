"""
JobRepository -- contract for job persistence.

Defines all storage operations the application needs.  Implementations
handle concurrency, transactions, and schema details internally.
"""
from __future__ import annotations

from typing import Protocol


class JobRepository(Protocol):
    def initialize(self) -> None:
        """Set up the storage backend (create tables, etc.)."""
        ...

    def find_by_idempotency_key(self, user_id: str, key: str) -> dict | None:
        """Find an existing job by ``(user_id, idempotency_key)``.

        Returns ``None`` if not found.
        """
        ...

    def count_active_jobs(self, user_id: str) -> int:
        """Count jobs in PENDING or RUNNING state for a user."""
        ...

    def insert_if_no_overlap(self, job: dict) -> tuple[str, dict | None]:
        """Atomically check for time-window overlap and insert.

        Returns ``("created", job)`` on success,
        ``("overlap", None)`` on time-window conflict,
        ``("idempotent", existing_job)`` on concurrent duplicate key.
        """
        ...

    def find_by_id(self, job_id: str, user_id: str) -> dict | None:
        """Find a single job by id, scoped to user."""
        ...

    def find_by_id_unscoped(self, job_id: str) -> dict | None:
        """Find a job by id without user scoping (used by MQTT handler)."""
        ...

    def list_by_user(self, user_id: str) -> list[dict]:
        """Return all jobs belonging to a user."""
        ...

    def update_state(
        self, job_id: str, state: str, error_message: str | None,
    ) -> dict | None:
        """Update job state and ``updated_at``.

        Returns the updated job or ``None`` if not found.
        """
        ...
