#!/usr/bin/env python3
"""
Worker stub for the backend technical exercise.

Subscribes to MQTT topic `jobs/dispatch`, simulates async processing,
and publishes state transitions on `jobs/result`.

Behaviour is DETERMINISTIC so the test harness can verify candidate
implementations reproducibly:
  - On dispatch: immediately publish state=RUNNING
  - Sleep WORKER_PROCESSING_SECONDS (default 1.0)
  - If the job targets asset_id == "asset-fault" -> publish state=FAILED
  - Otherwise -> publish state=COMPLETED

Environment variables:
  MQTT_HOST                (default: localhost)
  MQTT_PORT                (default: 1883)
  WORKER_PROCESSING_SECONDS (default: 1.0)

Requires: paho-mqtt
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
PROCESSING_SECONDS = float(os.environ.get("WORKER_PROCESSING_SECONDS", "1.0"))

TOPIC_DISPATCH = "jobs/dispatch"
TOPIC_RESULT = "jobs/result"
FAULT_ASSET_ID = "asset-fault"

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
log = logging.getLogger("worker")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
           f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def _publish_result(client: mqtt.Client, job_id: str, state: str, error: str | None = None) -> None:
    payload = {"job_id": job_id, "state": state, "timestamp": _iso_now()}
    if error is not None:
        payload["error_message"] = error
    client.publish(TOPIC_RESULT, json.dumps(payload), qos=0)
    log.info(f"published state={state} job_id={job_id}")


def _process_dispatch(client: mqtt.Client, payload: dict) -> None:
    job_id = payload.get("job_id")
    asset_id = payload.get("asset_id")
    if not job_id or not asset_id:
        log.warning(f"ignoring malformed dispatch: {payload}")
        return

    # State 1: RUNNING (published immediately)
    _publish_result(client, job_id, "RUNNING")

    # Simulate work
    time.sleep(PROCESSING_SECONDS)

    # State 2: terminal — deterministic by asset_id
    if asset_id == FAULT_ASSET_ID:
        _publish_result(client, job_id, "FAILED",
                        error="Simulated worker failure (asset-fault)")
    else:
        _publish_result(client, job_id, "COMPLETED")


def _on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        log.info(f"connected to mqtt://{MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(TOPIC_DISPATCH, qos=0)
        log.info(f"subscribed to {TOPIC_DISPATCH}")
    else:
        log.error(f"mqtt connection failed rc={rc}")


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        log.warning(f"bad payload on {msg.topic}: {e}")
        return
    log.info(f"received dispatch job_id={payload.get('job_id')} "
             f"asset_id={payload.get('asset_id')}")
    # Run the work in a separate thread so we don't block the MQTT loop
    threading.Thread(target=_process_dispatch, args=(client, payload), daemon=True).start()


def main() -> int:
    client = mqtt.Client(
        client_id=f"worker-{os.getpid()}",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    client.on_connect = _on_connect
    client.on_message = _on_message

    # Reconnect logic: paho's loop_forever handles reconnects automatically.
    log.info(f"starting worker; will connect to mqtt://{MQTT_HOST}:{MQTT_PORT}")
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    except Exception as e:
        log.error(f"initial connect failed: {e}")
        # Keep trying — useful when the broker is still starting up in docker-compose
        client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)

    # Graceful shutdown
    def _stop(*_):
        log.info("shutting down")
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    client.loop_forever(retry_first_connection=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
