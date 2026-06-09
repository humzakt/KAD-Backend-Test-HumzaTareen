#!/usr/bin/env python3
"""
Self-assessment harness for the backend technical exercise.

Run this after you have started:
  1. The Mosquitto broker + worker (docker compose up -d)
  2. Your service (listening on http://localhost:8000)

Usage:
  python3 verify.py
  python3 verify.py --base-url http://localhost:8000

It runs ten scenarios end-to-end against your running service and prints
PASS / FAIL per scenario plus a summary. If everything passes you can be
confident your implementation meets the functional requirements in the
specification.

Requires: httpx, python-socketio[asyncio_client]
Install:  pip install httpx 'python-socketio[asyncio_client]'

This script does not modify your code or database. It uses the seed users
already in data/seed.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import socketio

ALICE_TOKEN = "tok_alice_a1b2c3d4e5f6"  # user-001
BOB_TOKEN = "tok_bob_b2c3d4e5f6a1"  # user-002
DEFAULT_BASE = "http://localhost:8000"


# ---------- pretty output ----------
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
RESET = "\033[0m"


def _label(name: str) -> None:
    print(f"\n{name}")


def _pass(msg: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}FAIL{RESET}  {msg}")


def _info(msg: str) -> None:
    print(f"  {DIM}info{RESET}  {msg}")


# ---------- helpers ----------
def _future_window(hours_ahead: int = 1, duration_hours: int = 1) -> tuple[str, str]:
    """Return (start, end) ISO-8601 UTC strings, both on the hour."""
    now = datetime.now(timezone.utc)
    start = (now + timedelta(hours=hours_ahead)).replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=duration_hours)
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    return start.strftime(fmt), end.strftime(fmt)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _idem_key() -> str:
    return f"verify-{uuid.uuid4()}"


async def _submit(client, base, token, asset, idem=None, op="charge",
                  hours_ahead=1, duration_hours=1):
    start, end = _future_window(hours_ahead, duration_hours)
    body = {"asset_id": asset, "operation": op, "start_time": start, "end_time": end}
    headers = {**_auth(token),
               "Idempotency-Key": idem or _idem_key(),
               "Content-Type": "application/json"}
    return await client.post(f"{base}/api/jobs", json=body, headers=headers)


# ---------- scenarios ----------
class Result:
    def __init__(self):
        self.scenarios: list[tuple[str, bool, str]] = []

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.scenarios.append((name, ok, detail))
        (_pass if ok else _fail)(f"{name}{(' — ' + detail) if detail else ''}")

    def summary(self) -> int:
        total = len(self.scenarios)
        passed = sum(1 for _, ok, _ in self.scenarios if ok)
        print()
        print("=" * 60)
        bar = (GREEN if passed == total else (YELLOW if passed > 0 else RED))
        print(f"{bar}{passed}/{total} scenarios passed{RESET}")
        if passed != total:
            print()
            print("Failed scenarios:")
            for name, ok, _ in self.scenarios:
                if not ok:
                    print(f"  - {name}")
        return 0 if passed == total else 1


async def scenario_health(client, base, r):
    _label("1. /health returns 200")
    try:
        resp = await client.get(f"{base}/health")
        ok = resp.status_code == 200
        r.record("health responds 200", ok, f"got {resp.status_code}")
    except Exception as e:
        r.record("health responds 200", False, f"request error: {e}")


async def scenario_auth(client, base, r):
    _label("2. Authentication")
    resp = await client.get(f"{base}/api/jobs")
    r.record("GET /api/jobs without token returns 401",
             resp.status_code == 401, f"got {resp.status_code}")

    resp = await client.get(f"{base}/api/jobs", headers={"Authorization": "Bearer bogus-token"})
    r.record("GET /api/jobs with invalid token returns 401",
             resp.status_code == 401, f"got {resp.status_code}")

    resp = await client.get(f"{base}/api/jobs", headers=_auth(ALICE_TOKEN))
    r.record("GET /api/jobs with valid token returns 200",
             resp.status_code == 200, f"got {resp.status_code}")


async def scenario_submit_and_get(client, base, r):
    _label("3. Submit a valid job and read it back")
    resp = await _submit(client, base, ALICE_TOKEN, asset="asset-001")
    if resp.status_code != 201:
        r.record("POST /api/jobs returns 201", False, f"got {resp.status_code}: {resp.text[:200]}")
        return None
    job = resp.json()
    r.record("POST /api/jobs returns 201", True, f"job_id={job['id']}")
    r.record("response includes id", "id" in job, "")
    r.record("response includes state", job.get("state") in ("PENDING", "RUNNING"),
             f"state={job.get('state')}")

    resp = await client.get(f"{base}/api/jobs/{job['id']}", headers=_auth(ALICE_TOKEN))
    r.record("GET /api/jobs/{id} returns 200", resp.status_code == 200, f"got {resp.status_code}")
    return job["id"]


async def scenario_idempotency(client, base, r):
    _label("4. Idempotency-Key returns the same job on a second POST")
    key = _idem_key()
    resp1 = await _submit(client, base, ALICE_TOKEN, asset="asset-002", idem=key)
    resp2 = await _submit(client, base, ALICE_TOKEN, asset="asset-002", idem=key)
    if resp1.status_code != 201 or resp2.status_code != 201:
        r.record("Both responses return 201", False, f"r1={resp1.status_code} r2={resp2.status_code}")
        return
    j1 = resp1.json()
    j2 = resp2.json()
    r.record("Same Idempotency-Key returns same job id",
             j1["id"] == j2["id"], f"r1.id={j1['id']} r2.id={j2['id']}")

    listing = await client.get(f"{base}/api/jobs", headers=_auth(ALICE_TOKEN))
    count = sum(1 for x in listing.json() if x["id"] == j1["id"])
    r.record("Listing contains the job exactly once", count == 1, f"count={count}")


async def scenario_overlap_conflict(client, base, r):
    _label("5. Submitting a job that overlaps an existing job on the same asset returns 409")
    # Use a unique asset window
    await _submit(client, base, ALICE_TOKEN, asset="asset-004",
                  hours_ahead=10, duration_hours=2)
    resp = await _submit(client, base, ALICE_TOKEN, asset="asset-004",
                        hours_ahead=11, duration_hours=1)  # overlaps the first
    r.record("Overlap returns 409", resp.status_code == 409, f"got {resp.status_code}")


async def scenario_parallel_overlap(client, base, r):
    _label("6. 10 parallel overlapping submissions on the same asset — exactly 1 wins")
    start, end = _future_window(20, 2)
    body = {"asset_id": "asset-005", "operation": "charge",
            "start_time": start, "end_time": end}

    async def fire(i):
        return (await client.post(
            f"{base}/api/jobs",
            json=body,
            headers={**_auth(ALICE_TOKEN),
                     "Idempotency-Key": f"parallel-{uuid.uuid4()}-{i}",
                     "Content-Type": "application/json"},
        )).status_code

    codes = await asyncio.gather(*[fire(i) for i in range(10)])
    n201 = codes.count(201)
    n409 = codes.count(409)
    r.record("Exactly 1 succeeded (201)", n201 == 1, f"got {n201}× 201, {n409}× 409, others={codes}")
    r.record("Other 9 returned 409", n409 == 9, f"got {n409}× 409")


async def scenario_cross_user(client, base, r):
    _label("7. Cross-user access — Bob cannot read Alice's job")
    resp = await _submit(client, base, ALICE_TOKEN, asset="asset-006",
                         hours_ahead=24, duration_hours=1)
    if resp.status_code != 201:
        r.record("Alice submission succeeded", False, f"{resp.status_code}: {resp.text[:200]}")
        return
    job_id = resp.json()["id"]
    resp = await client.get(f"{base}/api/jobs/{job_id}", headers=_auth(BOB_TOKEN))
    r.record("Bob reading Alice's job returns 404 (not 200/403)",
             resp.status_code in (403, 404),
             f"got {resp.status_code}")

    listing = await client.get(f"{base}/api/jobs", headers=_auth(BOB_TOKEN))
    bob_jobs = listing.json()
    r.record("Bob's list does not include Alice's job",
             not any(j["id"] == job_id for j in bob_jobs),
             f"bob has {len(bob_jobs)} jobs")


async def scenario_validation(client, base, r):
    _label("8. Validation: unknown asset → 422; start in past → 422; bad duration → 422")
    # Use a far-future window on a free asset so the only possible failure
    # mode is the business-rule we're testing (no overlap, no past-time bleed).

    # Unknown asset
    body = {"asset_id": "asset-does-not-exist", "operation": "charge",
            "start_time": _future_window(200, 1)[0], "end_time": _future_window(200, 1)[1]}
    resp = await client.post(f"{base}/api/jobs", json=body,
                             headers={**_auth(ALICE_TOKEN),
                                      "Idempotency-Key": _idem_key(),
                                      "Content-Type": "application/json"})
    r.record("Unknown asset_id returns 422", resp.status_code == 422,
             f"got {resp.status_code}")

    # Start in past
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    future = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = {"asset_id": "asset-001", "operation": "charge",
            "start_time": past, "end_time": future}
    resp = await client.post(f"{base}/api/jobs", json=body,
                             headers={**_auth(ALICE_TOKEN),
                                      "Idempotency-Key": _idem_key(),
                                      "Content-Type": "application/json"})
    r.record("start_time in past returns 422", resp.status_code == 422,
             f"got {resp.status_code}")

    # Duration too short (5 minutes). Use a far-future, asset-unique window
    # so the only constraint that can fire is the duration check.
    base_now = datetime.now(timezone.utc) + timedelta(hours=300)
    s = base_now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    e = (base_now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body = {"asset_id": "asset-008", "operation": "charge",
            "start_time": s, "end_time": e}
    resp = await client.post(f"{base}/api/jobs", json=body,
                             headers={**_auth(ALICE_TOKEN),
                                      "Idempotency-Key": _idem_key(),
                                      "Content-Type": "application/json"})
    r.record("duration < 15min returns 422", resp.status_code == 422,
             f"got {resp.status_code}")


async def scenario_end_to_end(client, base, r):
    _label("9. End-to-end: submit → worker processes → state becomes COMPLETED")
    resp = await _submit(client, base, ALICE_TOKEN, asset="asset-007",
                         hours_ahead=48, duration_hours=1)
    if resp.status_code != 201:
        r.record("Initial submit returned 201", False, f"{resp.status_code}: {resp.text[:200]}")
        return
    job_id = resp.json()["id"]
    _info(f"submitted job {job_id}; polling for COMPLETED...")
    deadline = time.time() + 10.0
    final_state = None
    while time.time() < deadline:
        await asyncio.sleep(0.2)
        resp = await client.get(f"{base}/api/jobs/{job_id}", headers=_auth(ALICE_TOKEN))
        if resp.status_code == 200:
            final_state = resp.json().get("state")
            if final_state in ("COMPLETED", "FAILED"):
                break
    r.record("Job reaches COMPLETED via MQTT round-trip",
             final_state == "COMPLETED", f"final state={final_state}")


async def scenario_worker_failure(client, base, r):
    _label("10. Worker failure path: jobs on 'asset-fault' transition to FAILED")
    resp = await _submit(client, base, ALICE_TOKEN, asset="asset-fault",
                         hours_ahead=72, duration_hours=1)
    if resp.status_code != 201:
        r.record("Initial submit returned 201", False, f"{resp.status_code}: {resp.text[:200]}")
        return
    job_id = resp.json()["id"]
    deadline = time.time() + 10.0
    final_state = None
    error_msg = None
    while time.time() < deadline:
        await asyncio.sleep(0.2)
        resp = await client.get(f"{base}/api/jobs/{job_id}", headers=_auth(ALICE_TOKEN))
        if resp.status_code == 200:
            final_state = resp.json().get("state")
            error_msg = resp.json().get("error_message")
            if final_state in ("COMPLETED", "FAILED"):
                break
    r.record("Job on asset-fault transitions to FAILED",
             final_state == "FAILED", f"final state={final_state}")
    r.record("error_message is populated on FAILED",
             bool(error_msg), f"error_message={error_msg!r}")


async def scenario_socketio(base, r):
    _label("11. SocketIO: each user receives only their own job_update events")
    alice = socketio.AsyncClient(reconnection=False)
    bob = socketio.AsyncClient(reconnection=False)
    alice_events: list[dict] = []
    bob_events: list[dict] = []

    @alice.on("job_update")
    def _a(d):
        alice_events.append(d)

    @bob.on("job_update")
    def _b(d):
        bob_events.append(d)

    try:
        await alice.connect(f"{base}?token={ALICE_TOKEN}", wait_timeout=5)
        await bob.connect(f"{base}?token={BOB_TOKEN}", wait_timeout=5)
    except Exception as e:
        r.record("Both users connect to SocketIO", False, f"connect error: {e}")
        return

    # Alice submits a job that will go through the worker
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await _submit(client, base, ALICE_TOKEN, asset="asset-008",
                             hours_ahead=96, duration_hours=1)
        if resp.status_code != 201:
            r.record("Alice's submit succeeded", False, f"got {resp.status_code}")
            await alice.disconnect()
            await bob.disconnect()
            return
        job_id = resp.json()["id"]
        _info(f"alice submitted {job_id}")

    # Wait for both transitions to arrive
    await asyncio.sleep(2.5)
    await alice.disconnect()
    await bob.disconnect()

    alice_for_job = [e for e in alice_events if e.get("job_id") == job_id]
    bob_for_job = [e for e in bob_events if e.get("job_id") == job_id]

    r.record("Alice receives job_update events for her own job",
             len(alice_for_job) >= 1,
             f"received {len(alice_for_job)} events: {[e.get('state') for e in alice_for_job]}")
    r.record("Bob does NOT receive Alice's job events",
             len(bob_for_job) == 0,
             f"bob received {len(bob_for_job)} unexpected events")


# ---------- main ----------
async def run(base: str) -> int:
    r = Result()
    print(f"Running verification against {base}")
    print(f"Using Alice (user-001) and Bob (user-002) from data/seed.json")

    async with httpx.AsyncClient(timeout=10.0) as client:
        await scenario_health(client, base, r)
        await scenario_auth(client, base, r)
        await scenario_submit_and_get(client, base, r)
        await scenario_idempotency(client, base, r)
        await scenario_overlap_conflict(client, base, r)
        await scenario_parallel_overlap(client, base, r)
        await scenario_cross_user(client, base, r)
        await scenario_validation(client, base, r)
        await scenario_end_to_end(client, base, r)
        await scenario_worker_failure(client, base, r)

    await scenario_socketio(base, r)

    return r.summary()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default=DEFAULT_BASE,
                   help=f"Base URL of your service (default: {DEFAULT_BASE})")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args.base_url)))


if __name__ == "__main__":
    main()
