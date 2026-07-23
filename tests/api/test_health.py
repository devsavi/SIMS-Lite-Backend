"""
Tests for health endpoints.

These tests use the ASGI test client and mock out service dependencies
so no real database/Redis/MinIO is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient):
    """GET /api/v1/health should return 200 with status ok."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_system_health_all_ok(client: AsyncClient):
    """
    GET /api/v1/system/health should return 200 when all services are healthy.
    """
    ok_result = {"status": "ok", "latency_ms": 1.0}

    with (
        patch("app.api.v1.endpoints.system.check_database", new_callable=AsyncMock, return_value=ok_result),
        patch("app.api.v1.endpoints.system.check_redis", new_callable=AsyncMock, return_value=ok_result),
        patch("app.storage.minio_client.StorageService.health_check", new_callable=AsyncMock, return_value=ok_result),
    ):
        response = await client.get("/api/v1/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "database" in body["services"]
    assert "redis" in body["services"]
    assert "minio" in body["services"]


@pytest.mark.asyncio
async def test_system_health_degraded_when_service_down(client: AsyncClient):
    """
    GET /api/v1/system/health should return 503 when any service is unhealthy.
    """
    ok_result = {"status": "ok", "latency_ms": 1.0}
    error_result = {"status": "error", "error": "Connection refused"}

    with (
        patch("app.api.v1.endpoints.system.check_database", new_callable=AsyncMock, return_value=error_result),
        patch("app.api.v1.endpoints.system.check_redis", new_callable=AsyncMock, return_value=ok_result),
        patch("app.storage.minio_client.StorageService.health_check", new_callable=AsyncMock, return_value=ok_result),
    ):
        response = await client.get("/api/v1/system/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_root_redirects_to_docs(client: AsyncClient):
    """GET / should redirect to /docs."""
    response = await client.get("/", follow_redirects=False)
    assert response.status_code in (301, 302, 307, 308)
    assert "/docs" in response.headers.get("location", "")
