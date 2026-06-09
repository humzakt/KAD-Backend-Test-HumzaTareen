"""
AuthProvider -- contract for authentication services.

Any implementation must resolve a bearer token to a user dict
or return None for invalid tokens.
"""
from __future__ import annotations

from typing import Protocol


class AuthProvider(Protocol):
    def authenticate(self, token: str) -> dict | None:
        """Given a bearer token, return the user dict or ``None``."""
        ...
