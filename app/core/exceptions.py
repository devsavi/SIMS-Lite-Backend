"""
Domain exception hierarchy and global FastAPI exception handlers.

All application errors derive from AppException so callers can catch
a single base type, while HTTP handlers translate them to structured
JSON responses with a consistent shape:

    {
        "status": "error",
        "code": "NOT_FOUND",
        "message": "Resource not found",
        "details": null,
        "request_id": "..."
    }
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, get_request_id

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------


class AppException(Exception):
    """Base class for all application-level exceptions."""

    http_status: int = 500
    error_code: str = "INTERNAL_ERROR"
    default_message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        details: Any = None,
        http_status: int | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.details = details
        if http_status is not None:
            self.http_status = http_status
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# Concrete exception types
# ---------------------------------------------------------------------------


class NotFoundError(AppException):
    http_status = 404
    error_code = "NOT_FOUND"
    default_message = "The requested resource was not found."


class ConflictError(AppException):
    http_status = 409
    error_code = "CONFLICT"
    default_message = "A resource with the given identifier already exists."


class ValidationError(AppException):
    http_status = 422
    error_code = "VALIDATION_ERROR"
    default_message = "Input validation failed."


class UnauthorizedError(AppException):
    http_status = 401
    error_code = "UNAUTHORIZED"
    default_message = "Authentication is required."


class ForbiddenError(AppException):
    http_status = 403
    error_code = "FORBIDDEN"
    default_message = "You do not have permission to perform this action."


class ServiceUnavailableError(AppException):
    http_status = 503
    error_code = "SERVICE_UNAVAILABLE"
    default_message = "A dependent service is currently unavailable."


class StorageError(AppException):
    http_status = 500
    error_code = "STORAGE_ERROR"
    default_message = "Object storage operation failed."


class DatabaseError(AppException):
    http_status = 500
    error_code = "DATABASE_ERROR"
    default_message = "A database error occurred."


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------


def _error_response(
    *,
    status_code: int,
    error_code: str,
    message: str,
    details: Any = None,
    request_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "code": error_code,
            "message": message,
            "details": details,
            "request_id": request_id or get_request_id(),
        },
    )


# ---------------------------------------------------------------------------
# FastAPI exception handlers
# ---------------------------------------------------------------------------


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        "Application exception",
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.http_status,
        path=str(request.url),
    )
    return _error_response(
        status_code=exc.http_status,
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    phrase = HTTPStatus(exc.status_code).phrase if exc.status_code in HTTPStatus._value2member_map_ else "Error"  # type: ignore[attr-defined]
    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=str(request.url),
    )
    return _error_response(
        status_code=exc.status_code,
        error_code=phrase.upper().replace(" ", "_"),
        message=str(exc.detail),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    logger.warning(
        "Request validation failed",
        errors=errors,
        path=str(request.url),
    )
    return _error_response(
        status_code=422,
        error_code="VALIDATION_ERROR",
        message="Request validation failed.",
        details=errors,
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception(
        "Unhandled exception",
        exc_info=exc,
        path=str(request.url),
    )
    return _error_response(
        status_code=500,
        error_code="INTERNAL_ERROR",
        message="An unexpected internal error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all global exception handlers to the FastAPI application."""
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
