"""
MQTTBrokerService -- MQTT pub/sub via paho-mqtt.

Runs paho's network loop in a background daemon thread (``loop_start``).
Publishes job dispatches to ``jobs/dispatch`` with the full 5-field payload.
Subscribes to ``jobs/result`` and validates state transitions before
invoking the result callback.

Threading note
--------------
``on_message`` runs in paho's thread, **not** the asyncio event loop.
The result callback (set by ``app.py``) is responsible for bridging to
async land via ``asyncio.run_coroutine_threadsafe``.

Implements :class:`~service.providers.broker.MessageBroker`.
"""
from __future__ import annotations

import json
from typing import Callable

import paho.mqtt.client as mqtt

from service import config
from service import constants as C
from service.logger import get_logger
from service.models import is_valid_transition
from service.providers.repository import JobRepository

log = get_logger("broker")


class MQTTBrokerService:
    """Manages MQTT connection, dispatch publishing, and result subscription."""

    def __init__(self, repository: JobRepository) -> None:
        self._client: mqtt.Client | None = None
        self._on_result: Callable[[dict], None] | None = None
        self._repository = repository

    def start(self, on_result: Callable[[dict], None]) -> None:
        self._on_result = on_result
        self._client = mqtt.Client(
            client_id=C.MQTT_CLIENT_ID,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(
            config.MQTT_HOST, config.MQTT_PORT,
            keepalive=C.MQTT_KEEPALIVE_SECONDS,
        )
        self._client.loop_start()
        log.info(
            f"connecting to mqtt://{config.MQTT_HOST}:{config.MQTT_PORT}",
        )

    def stop(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            log.info("disconnected from MQTT")

    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected()

    def publish_dispatch(self, job: dict) -> None:
        payload = {
            C.FIELD_JOB_ID: job["id"],
            C.FIELD_ASSET_ID: job[C.FIELD_ASSET_ID],
            C.FIELD_START_TIME: job[C.FIELD_START_TIME],
            C.FIELD_END_TIME: job[C.FIELD_END_TIME],
            C.FIELD_OPERATION: job[C.FIELD_OPERATION],
        }
        self._client.publish(
            C.TOPIC_DISPATCH, json.dumps(payload), qos=C.MQTT_QOS,
        )
        log.info(
            f"dispatched job_id={job['id']} asset={job[C.FIELD_ASSET_ID]}",
        )

    # -- paho callbacks (run in paho's background thread) ------------------

    def _on_connect(
        self, client: mqtt.Client, userdata: object,
        flags: object, rc: int, properties: object = None,
    ) -> None:
        if rc == 0:
            client.subscribe(C.TOPIC_RESULT, qos=C.MQTT_QOS)
            log.info(f"subscribed to {C.TOPIC_RESULT}")
        else:
            log.error(f"MQTT connect failed rc={rc}")

    def _on_message(
        self, client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage,
    ) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            log.warning(f"malformed MQTT message: {exc}")
            return

        job_id = payload.get(C.FIELD_JOB_ID)
        new_state = payload.get(C.FIELD_STATE)
        if not job_id or not new_state:
            log.warning("MQTT result missing job_id or state, ignoring")
            return

        current = self._repository.find_by_id_unscoped(job_id)
        if current is None:
            log.warning(f"result for unknown job_id={job_id}, ignoring")
            return

        if not is_valid_transition(current[C.FIELD_STATE], new_state):
            log.warning(
                f"invalid transition {current[C.FIELD_STATE]}->{new_state} "
                f"for job_id={job_id}, ignoring",
            )
            return

        error_msg = payload.get(C.FIELD_ERROR_MESSAGE)
        updated = self._repository.update_state(job_id, new_state, error_msg)
        log.info(
            f"state updated job_id={job_id} "
            f"{current[C.FIELD_STATE]}->{new_state}",
        )

        if updated and self._on_result:
            self._on_result(updated)
