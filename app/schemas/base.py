"""
Shared Pydantic v2 base schemas and response envelopes.

Every API response should use one of the generic wrappers defined here
to ensure a consistent structure clients can rely on.

Success single item::

    {"status": "success", "data": {...}}

Success collection::

    {
        "status": "success",
        "data": [...],
        "pagination": {"page": 1, "size": 20, "total": 100, "pages": 5}
    }

Error (produced by exception handlers in core.exceptions)::

    {
        "status": "error",
        "code": "NOT_FOUND",
        "message": "...",
        "details": null,
        "request_id": "..."
    }
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DataT = TypeVar("DataT")


class AppBaseModel(BaseModel):
    """Project-wide Pydantic base with sensible defaults."""

    model_config = ConfigDict(
        from_attributes=True,       # support ORM model -> schema
        populate_by_name=True,      # accept both alias and field name
        str_strip_whitespace=True,
    )


class SuccessResponse(AppBaseModel, Generic[DataT]):
    """Envelope for a single-resource success response."""

    status: str = Field(default="success")
    data: DataT


class PaginationMeta(AppBaseModel):
    """Pagination metadata for collection responses."""

    page: int = Field(ge=1)
    size: int = Field(ge=1)
    total: int = Field(ge=0)
    pages: int = Field(ge=0)


class PaginatedResponse(AppBaseModel, Generic[DataT]):
    """Envelope for paginated collection responses."""

    status: str = Field(default="success")
    data: list[DataT]
    pagination: PaginationMeta


class ErrorResponse(AppBaseModel):
    """Envelope for error responses (mirrors exception handlers)."""

    status: str = Field(default="error")
    code: str
    message: str
    details: object | None = None
    request_id: str | None = None
