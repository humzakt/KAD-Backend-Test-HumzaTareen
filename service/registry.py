"""
Service Registry -- central dependency container.

Provides a type-safe way to register and resolve service implementations
against their provider protocols.  All wiring happens once at startup
in ``app.py``.
"""
from __future__ import annotations

from typing import Type, TypeVar

T = TypeVar("T")


class ServiceRegistry:
    """Maps Protocol types to their concrete implementations."""

    def __init__(self) -> None:
        self._services: dict[type, object] = {}

    def register(self, protocol: Type[T], instance: T) -> None:
        """Register a service implementation for a given protocol."""
        self._services[protocol] = instance

    def resolve(self, protocol: Type[T]) -> T:
        """Resolve the registered implementation for a protocol.

        Raises ``RuntimeError`` if no implementation is registered.
        """
        instance = self._services.get(protocol)
        if instance is None:
            raise RuntimeError(
                f"No service registered for {protocol.__name__}. "
                f"Registered: {[t.__name__ for t in self._services]}"
            )
        return instance  # type: ignore[return-value]

