"""Unit tests for the exception hierarchy."""

import pytest

from app.core.exceptions import (
    AppException,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)


def test_not_found_defaults():
    exc = NotFoundError()
    assert exc.http_status == 404
    assert exc.error_code == "NOT_FOUND"
    assert exc.message


def test_custom_message():
    exc = NotFoundError("Student not found")
    assert exc.message == "Student not found"


def test_conflict_error():
    exc = ConflictError()
    assert exc.http_status == 409


def test_unauthorized_error():
    exc = UnauthorizedError()
    assert exc.http_status == 401


def test_forbidden_error():
    exc = ForbiddenError()
    assert exc.http_status == 403


def test_app_exception_is_base():
    assert issubclass(NotFoundError, AppException)
    assert issubclass(ConflictError, AppException)
