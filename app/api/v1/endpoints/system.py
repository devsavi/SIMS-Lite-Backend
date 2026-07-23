"""
GET /api/v1/system/health — deep readiness probe.

Checks all downstream dependencies:
  - PostgreSQL
  - Redis
  - MinIO

Returns 200 when all services are healthy, 503 otherwise.
"""

from __future__ import annotations

import asyncio
import platform
import sys
from typing import Any

import psutil
from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.core.logging import get_logger
from app.database.health import check_database
from app.core.redis import check_redis
from app.storage.minio_client import StorageService

logger = get_logger(__name__)
router = APIRouter()


class ServiceStatus(BaseModel):
    status: str
    latency_ms: float | None = None
    error: str | None = None


class SystemInfo(BaseModel):
    python_version: str
    platform: str
    cpu_percent: float
    memory_percent: float


class SystemHealthResponse(BaseModel):
    status: str
    services: dict[str, ServiceStatus]
    system: SystemInfo
    version: str


@router.get(
    "/health",
    response_model=SystemHealthResponse,
    summary="Readiness probe — checks all downstream services",
)
async def system_health(response: Response) -> SystemHealthResponse:
    from app import __version__

    _storage = StorageService()

    # Run all checks concurrently
    db_result, redis_result, minio_result = await asyncio.gather(
        check_database(),
        check_redis(),
        _storage.health_check(),
        return_exceptions=True,
    )

    def _to_status(result: Any) -> ServiceStatus:
        if isinstance(result, Exception):
            return ServiceStatus(status="error", error=str(result))
        return ServiceStatus(**result)

    services = {
        "database": _to_status(db_result),
        "redis": _to_status(redis_result),
        "minio": _to_status(minio_result),
    }

    overall_ok = all(s.status == "ok" for s in services.values())
    overall_status = "ok" if overall_ok else "degraded"

    if not overall_ok:
        response.status_code = 503

    system_info = SystemInfo(
        python_version=sys.version,
        platform=platform.platform(),
        cpu_percent=psutil.cpu_percent(interval=None),
        memory_percent=psutil.virtual_memory().percent,
    )

    return SystemHealthResponse(
        status=overall_status,
        services=services,
        system=system_info,
        version=__version__,
    )
