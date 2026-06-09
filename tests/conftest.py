"""
Shared test fixtures and helpers.

Tests run against the live service (``http://localhost:8000``) with the
real MQTT broker from ``docker compose``.  No mocking -- same conditions
as ``verify.py``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

BASE_URL = "http://localhost:8000"
ALICE_TOKEN = "tok_alice_a1b2c3d4e5f6"
TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%S.000Z"


@pytest.fixture()
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        yield c


def auth_headers(token: str = ALICE_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_idempotency_key() -> str:
    return f"test-{uuid.uuid4()}"


def future_window(
    hours_ahead: int = 1, duration_hours: int = 1,
) -> tuple[str, str]:
    """Return a (start, end) ISO-8601 UTC pair safely in the future."""
    now = datetime.now(timezone.utc)
    start = (now + timedelta(hours=hours_ahead)).replace(
        minute=0, second=0, microsecond=0,
    )
    end = start + timedelta(hours=duration_hours)
    return start.strftime(TIMESTAMP_FMT), end.strftime(TIMESTAMP_FMT)
