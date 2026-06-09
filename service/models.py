"""
Domain models, Pydantic schemas, and state machine definition.

``JobState``  -- enum backed by constants for the four job states.
``VALID_TRANSITIONS`` -- the allowed state machine edges.
``is_valid_transition`` -- guard function used by the broker service.
``JobCreate`` -- inbound POST /api/jobs request body.
``JobResponse`` -- outbound job representation for all endpoints.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from service.constants import (
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_PENDING,
    STATE_RUNNING,
)


class JobState(str, Enum):
    PENDING = STATE_PENDING
    RUNNING = STATE_RUNNING
    COMPLETED = STATE_COMPLETED
    FAILED = STATE_FAILED


VALID_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.PENDING: {JobState.RUNNING, JobState.COMPLETED, JobState.FAILED},
    JobState.RUNNING: {JobState.COMPLETED, JobState.FAILED},
}


def is_valid_transition(current: str, proposed: str) -> bool:
    """Return True if the state machine allows *current* -> *proposed*."""
    try:
        current_state = JobState(current)
        proposed_state = JobState(proposed)
    except ValueError:
        return False
    allowed = VALID_TRANSITIONS.get(current_state)
    return allowed is not None and proposed_state in allowed


class JobCreate(BaseModel):
    asset_id: str
    operation: str
    start_time: datetime
    end_time: datetime


class JobResponse(BaseModel):
    id: str
    asset_id: str
    operation: str
    start_time: str
    end_time: str
    state: str
    error_message: str | None
    created_at: str
    updated_at: str
