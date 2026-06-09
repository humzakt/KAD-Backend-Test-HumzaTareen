"""
MessageBroker -- contract for pub/sub messaging (MQTT).

Handles publishing dispatch messages to the worker and subscribing
to result messages.  The ``on_result`` callback bridges back into
the application layer.
"""
from __future__ import annotations

from typing import Callable, Protocol


class MessageBroker(Protocol):
    def start(self, on_result: Callable[[dict], None]) -> None:
        """Connect, subscribe, and begin processing messages."""
        ...

    def stop(self) -> None:
        """Disconnect and stop processing."""
        ...

    def publish_dispatch(self, job: dict) -> None:
        """Publish a job dispatch message to the worker."""
        ...

    def is_connected(self) -> bool:
        """Return ``True`` if the broker connection is alive."""
        ...
