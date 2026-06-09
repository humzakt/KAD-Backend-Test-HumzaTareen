"""
ASGI application assembly and lifecycle management.

Wires all services into the :class:`~service.registry.ServiceRegistry`,
mounts Socket.IO alongside FastAPI, and manages startup/shutdown of
MQTT and database connections.

MQTT / Socket.IO threading bridge
----------------------------------
paho-mqtt's ``on_message`` callback runs in a background OS thread.
Socket.IO's ``emit()`` is an asyncio coroutine.  We bridge using
``asyncio.run_coroutine_threadsafe()`` to schedule the emit on the
main event loop from paho's thread.
"""
from __future__ import annotations

import asyncio
import os

import socketio
import uvicorn
from fastapi import FastAPI

from service import config
from service import constants as C
from service.api.dependencies import init_dependencies
from service.api.error_handlers import register_error_handlers
from service.api.routes import api_router, health_router
from service.logger import get_logger
from service.providers.auth import AuthProvider
from service.providers.broker import MessageBroker
from service.providers.notifier import RealtimeNotifier
from service.providers.repository import JobRepository
from service.registry import ServiceRegistry
from service.services.auth_service import TokenAuthService
from service.services.broker_service import MQTTBrokerService
from service.services.job_orchestrator import JobOrchestrator
from service.services.job_repository import SQLiteJobRepository
from service.services.notifier_service import SocketIONotifierService
from service.services.validation_service import JobValidationService

log = get_logger("app")

# ---------------------------------------------------------------------------
# ASGI assembly
# ---------------------------------------------------------------------------
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
fastapi_app = FastAPI(title="Job Scheduling API")
fastapi_app.include_router(health_router)
fastapi_app.include_router(api_router)
register_error_handlers(fastapi_app)
asgi_app = socketio.ASGIApp(sio, fastapi_app)

# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------
registry = ServiceRegistry()

# Remove stale DB on fresh start so verify.py is deterministic
if os.path.exists(config.DB_PATH):
    os.remove(config.DB_PATH)

repo = SQLiteJobRepository()
notifier = SocketIONotifierService(sio)

registry.register(AuthProvider, TokenAuthService())
registry.register(JobRepository, repo)
registry.register(JobValidationService, JobValidationService())
registry.register(RealtimeNotifier, notifier)

broker = MQTTBrokerService(repo)
registry.register(MessageBroker, broker)
registry.register(JobOrchestrator, JobOrchestrator(registry))

init_dependencies(registry)

# ---------------------------------------------------------------------------
# MQTT -> Socket.IO bridge (threading boundary)
# ---------------------------------------------------------------------------
_loop: asyncio.AbstractEventLoop | None = None


def _on_mqtt_result(updated_job: dict) -> None:
    """Called from paho's thread when a job state transition is persisted."""
    payload = {
        C.FIELD_JOB_ID: updated_job["id"],
        C.FIELD_STATE: updated_job[C.FIELD_STATE],
        C.FIELD_TIMESTAMP: updated_job["updated_at"],
    }
    user_id = updated_job["user_id"]
    if _loop and not _loop.is_closed():
        future = asyncio.run_coroutine_threadsafe(
            notifier.notify_job_update(user_id, payload), _loop,
        )
        future.result(timeout=C.SOCKETIO_EMIT_TIMEOUT_SECONDS)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@fastapi_app.on_event("startup")
async def startup() -> None:
    global _loop
    _loop = asyncio.get_running_loop()
    repo.initialize()
    broker.start(on_result=_on_mqtt_result)
    log.info(f"service started on port {config.PORT}")


@fastapi_app.on_event("shutdown")
async def shutdown() -> None:
    broker.stop()
    log.info("service stopped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(asgi_app, host="0.0.0.0", port=config.PORT)
