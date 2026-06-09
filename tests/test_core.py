"""
Required tests per PDF section 6.

Three tests exercising the spec's most critical properties:

1. **Idempotency** -- same Idempotency-Key returns the same job.
2. **Atomic concurrency** -- 10 parallel overlapping submissions produce
   exactly 1x201 and 9x409.
3. **MQTT round-trip** -- a submitted job reaches COMPLETED via the worker.

All tests hit the real running service and MQTT broker (no mocking).
"""
from __future__ import annotations

import asyncio
import time
import uuid

import httpx

from tests.conftest import (
    BASE_URL,
    auth_headers,
    future_window,
    make_idempotency_key,
)


def test_idempotency_same_key_returns_same_job(client: httpx.Client) -> None:
    """Same Idempotency-Key twice returns the same job, listed once."""
    key = make_idempotency_key()
    start, end = future_window(hours_ahead=50)
    body = {
        "asset_id": "asset-001",
        "operation": "charge",
        "start_time": start,
        "end_time": end,
    }
    headers = {**auth_headers(), "Idempotency-Key": key}

    r1 = client.post("/api/jobs", json=body, headers=headers)
    r2 = client.post("/api/jobs", json=body, headers=headers)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"], "Idempotent replay must return same job id"

    listing = client.get("/api/jobs", headers=auth_headers())
    ids = [j["id"] for j in listing.json()]
    assert ids.count(r1.json()["id"]) == 1, "Job must appear exactly once in listing"


def test_atomic_overlap_exactly_one_wins() -> None:
    """10 parallel overlapping submissions -> exactly 1x201 and 9x409."""

    async def _run() -> None:
        start, end = future_window(hours_ahead=200, duration_hours=2)
        body = {
            "asset_id": "asset-003",
            "operation": "charge",
            "start_time": start,
            "end_time": end,
        }

        async def fire(i: int) -> int:
            async with httpx.AsyncClient(
                base_url=BASE_URL, timeout=10,
            ) as c:
                headers = {
                    **auth_headers(),
                    "Idempotency-Key": f"race-{uuid.uuid4()}-{i}",
                }
                r = await c.post("/api/jobs", json=body, headers=headers)
                return r.status_code

        codes = await asyncio.gather(*[fire(i) for i in range(10)])
        assert codes.count(201) == 1, f"Expected 1x201, got {codes}"
        assert codes.count(409) == 9, f"Expected 9x409, got {codes}"

    asyncio.run(_run())


def test_mqtt_roundtrip_job_reaches_completed(client: httpx.Client) -> None:
    """Submit a job -> worker processes it -> state becomes COMPLETED."""
    start, end = future_window(hours_ahead=250)
    body = {
        "asset_id": "asset-002",
        "operation": "charge",
        "start_time": start,
        "end_time": end,
    }
    headers = {**auth_headers(), "Idempotency-Key": make_idempotency_key()}

    r = client.post("/api/jobs", json=body, headers=headers)
    assert r.status_code == 201
    job_id = r.json()["id"]

    deadline = time.time() + 10
    state = None
    while time.time() < deadline:
        time.sleep(0.3)
        r = client.get(f"/api/jobs/{job_id}", headers=auth_headers())
        state = r.json().get("state")
        if state == "COMPLETED":
            break

    assert state == "COMPLETED", f"Expected COMPLETED, got {state}"
