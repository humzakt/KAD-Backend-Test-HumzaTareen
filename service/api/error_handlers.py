"""
Custom exception handlers for the 400-vs-422 split.

FastAPI returns 422 by default for Pydantic validation errors (malformed
JSON, bad timestamps).  The PDF spec maps these to 400 Bad Request.
Business rule violations are raised explicitly as 422 in the routes and
orchestrator.
"""
from __future__ import annotations

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=HTTPStatus.BAD_REQUEST,
            content={"detail": str(exc)},
        )
