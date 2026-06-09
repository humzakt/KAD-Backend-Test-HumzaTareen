"""
RealtimeNotifier -- contract for pushing real-time events to clients.

Implementations handle connection auth, per-user scoping, and
transport details (Socket.IO, SSE, etc.).
"""
from __future__ import annotations

from typing import Protocol


class RealtimeNotifier(Protocol):
    async def notify_job_update(self, user_id: str, payload: dict) -> None:
        """Send a ``job_update`` event to a specific user's connected clients."""
        ...
