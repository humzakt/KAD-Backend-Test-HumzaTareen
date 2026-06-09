"""
TokenAuthService -- Bearer token authentication.

Resolves static tokens from ``seed.json`` to user dicts.
Implements :class:`~service.providers.auth.AuthProvider`.

In production this would be replaced with JWT validation or an OAuth
provider; the protocol boundary makes that swap trivial.
"""
from __future__ import annotations

from service import config
from service.logger import get_logger

log = get_logger("auth")


class TokenAuthService:
    """Authenticates requests using static Bearer tokens from seed data."""

    def authenticate(self, token: str) -> dict | None:
        user = config.USERS_BY_TOKEN.get(token)
        if user:
            log.info(f"authenticated user_id={user['user_id']}")
        else:
            log.warning("invalid token attempted")
        return user
