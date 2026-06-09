"""
SocketIONotifierService -- real-time per-user event push via Socket.IO.

Manages Socket.IO connection authentication (token from query string),
per-user room assignment, and scoped event emission.  Users only ever
receive events for their own jobs.

Implements :class:`~service.providers.notifier.RealtimeNotifier`.
"""
from __future__ import annotations

import socketio

from service import config
from service import constants as C
from service.logger import get_logger

log = get_logger("notifier")


class SocketIONotifierService:
    """Socket.IO server wrapper with token-based auth and per-user rooms."""

    def __init__(self, sio: socketio.AsyncServer) -> None:
        self._sio = sio
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        @self._sio.event
        async def connect(sid: str, environ: dict, auth: object) -> None:
            qs = environ.get("QUERY_STRING", "")
            params = dict(
                pair.split("=", 1) for pair in qs.split("&") if "=" in pair
            )
            token = params.get(C.SOCKETIO_QUERY_TOKEN)
            user = config.USERS_BY_TOKEN.get(token) if token else None
            if not user:
                log.warning("Socket.IO connection rejected (invalid token)")
                raise ConnectionRefusedError(C.ErrorMessages.INVALID_TOKEN)
            user_id = user["user_id"]
            room = f"{C.SOCKETIO_ROOM_PREFIX}{user_id}"
            await self._sio.enter_room(sid, room)
            await self._sio.save_session(sid, {"user_id": user_id})
            log.info(f"Socket.IO connected sid={sid} user={user_id}")

        @self._sio.event
        async def disconnect(sid: str) -> None:
            log.info(f"Socket.IO disconnected sid={sid}")

    async def notify_job_update(self, user_id: str, payload: dict) -> None:
        room = f"{C.SOCKETIO_ROOM_PREFIX}{user_id}"
        await self._sio.emit(C.SOCKETIO_EVENT_JOB_UPDATE, payload, room=room)
        log.info(
            f"emitted {C.SOCKETIO_EVENT_JOB_UPDATE} to {room} "
            f"state={payload.get(C.FIELD_STATE)}",
        )
