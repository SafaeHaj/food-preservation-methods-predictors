"""Centralized exception translation.

The single place where an exception becomes an HTTP response. Every service calls
`install_exception_handlers(app)` and thereafter routes and services raise domain errors
from `shared.errors` and nothing else -- no `HTTPException`, no `try/except` that
swallows, no `{"error": ...}` return values.

Wire format, identical everywhere::

    {"error": {"code": "not_found",
               "message": "Paper 12 not found",
               "details": {...},           # optional
               "request_id": "a1b2c3d4"}}

Unexpected exceptions are logged with a traceback and reported as a generic 500. The
original message is never sent to the client -- it routinely contains file paths,
connection strings and SQL.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.errors import AppError
from shared.logging import get_request_id

logger = logging.getLogger(__name__)

#: HTTPException carries no domain code, so map its status onto the vocabulary that
#: `shared.errors` already defines. Keeps third-party/framework 4xx indistinguishable from
#: ours on the wire.
_STATUS_TO_CODE = {
    400: "business_rule_violation",
    401: "unauthenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    502: "upstream_unavailable",
    503: "service_unavailable",
    504: "upstream_timeout",
}


def _envelope(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    error: dict = {"code": code, "message": message, "request_id": get_request_id()}
    if details:
        error["details"] = jsonable_encoder(details)
    return JSONResponse(status_code=status_code, content={"error": error})


def install_exception_handlers(app: FastAPI) -> None:
    """Register the full translation table on `app`."""

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        # Expected conditions: log at WARNING without a traceback. A 404 is not an incident.
        logger.warning(
            "%s %s -> %s (%s): %s",
            request.method, request.url.path, exc.status_code, exc.code, exc.message,
        )
        return _envelope(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Surface the field-level detail; it is the only useful part of a 422 for a client.
        return _envelope(
            422,
            "validation_error",
            "Request validation failed",
            {"fields": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        code = _STATUS_TO_CODE.get(exc.status_code, "http_error")
        return _envelope(exc.status_code, code, detail)

    @app.exception_handler(IntegrityError)
    async def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        # A violated unique/FK constraint is a conflict, not a server fault.
        logger.warning("%s %s -> integrity error: %s", request.method, request.url.path, exc)
        return _envelope(409, "conflict", "The request conflicts with existing data")

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("%s %s -> database error", request.method, request.url.path)
        return _envelope(500, "database_error", "A database error occurred")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("%s %s -> unhandled %s", request.method, request.url.path, type(exc).__name__)
        return _envelope(500, "internal_error", "An unexpected error occurred")


__all__ = ["install_exception_handlers"]
