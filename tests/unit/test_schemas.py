"""Unit tests for shared response schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.base import (
    PaginatedResponse,
    PaginationMeta,
    SuccessResponse,
)


def test_success_response_wraps_data():
    resp = SuccessResponse(data={"id": 1, "name": "Test"})
    assert resp.status == "success"
    assert resp.data["name"] == "Test"


def test_paginated_response():
    meta = PaginationMeta(page=1, size=20, total=100, pages=5)
    resp = PaginatedResponse(data=[{"id": i} for i in range(3)], pagination=meta)
    assert resp.status == "success"
    assert len(resp.data) == 3
    assert resp.pagination.total == 100


def test_pagination_meta_validates_bounds():
    with pytest.raises(ValidationError):
        PaginationMeta(page=0, size=20, total=0, pages=0)  # page < 1
