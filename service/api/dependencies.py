"""
FastAPI dependency functions that bridge to the ServiceRegistry.

Route handlers declare these as ``Depends()`` parameters instead of
importing concrete service implementations directly.
"""
from __future__ import annotations

from fastapi import Header, HTTPException

from service import constants as C
from service.providers.auth import AuthProvider
from service.registry import ServiceRegistry

_registry: ServiceRegistry | None = None


def init_dependencies(registry: ServiceRegistry) -> None:
    global _registry
    _registry = registry


def get_registry() -> ServiceRegistry:
    if _registry is None:
        raise RuntimeError("Dependencies not initialised")
    return _registry


def get_current_user(authorization: str = Header(None)) -> dict:
    """Authenticate the request via Bearer token.

    Returns the user dict or raises 401.
    """
    if not authorization or not authorization.startswith(C.BEARER_PREFIX):
        raise HTTPException(
            status_code=C.HTTP_UNAUTHORIZED,
            detail=C.ErrorMessages.INVALID_TOKEN,
        )
    token = authorization.removeprefix(C.BEARER_PREFIX)
    auth: AuthProvider = get_registry().resolve(AuthProvider)
    user = auth.authenticate(token)
    if not user:
        raise HTTPException(
            status_code=C.HTTP_UNAUTHORIZED,
            detail=C.ErrorMessages.INVALID_TOKEN,
        )
    return user
