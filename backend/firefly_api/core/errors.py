"""Standardized error envelope and exception handlers (§8.4).

Every API error response uses the shape::

    {
        "errorCode": "<machine-readable token>",
        "errorDescription": "<human-readable message>",
        "details": {<optional context>}
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException


class FireflyError(Exception):
    """Base class for all API errors that map to the standard envelope."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        description: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.description = description
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code
        self.details: dict[str, Any] = details or {}
        super().__init__(description)


class NotFoundError(FireflyError):
    status_code = 404
    error_code = "not_found"


class ConflictError(FireflyError):
    status_code = 409
    error_code = "conflict"


class ValidationFailedError(FireflyError):
    status_code = 422
    error_code = "validation_error"


def _envelope(
    status_code: int,
    error_code: str,
    description: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "errorCode": error_code,
            "errorDescription": description,
            "details": details or {},
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(FireflyError)
    async def _firefly_error_handler(_request: Request, exc: FireflyError) -> JSONResponse:
        return _envelope(exc.status_code, exc.error_code, exc.description, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _envelope(
            422,
            "invalid_request",
            "Request body validation failed.",
            {"errors": exc.errors()},
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error_handler(
        _request: Request, exc: IntegrityError
    ) -> JSONResponse:
        # Generic fallback. Repositories/routes should normally translate
        # IntegrityError into ConflictError with a descriptive message before
        # it reaches this handler.
        return _envelope(
            409,
            "conflict",
            "Database constraint violated.",
            {"db_error": str(exc.orig) if exc.orig else str(exc)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # Cover 404s for unknown routes, etc.
        return _envelope(
            exc.status_code,
            _status_to_code(exc.status_code),
            str(exc.detail) if exc.detail else "",
        )


def _status_to_code(status: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        422: "validation_error",
        500: "internal_error",
        502: "bad_gateway",
        503: "service_unavailable",
        504: "gateway_timeout",
    }.get(status, "error")
