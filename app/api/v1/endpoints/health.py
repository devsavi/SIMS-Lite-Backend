"""
GET /api/v1/health — lightweight liveness probe.

Returns 200 if the application process is running.
No downstream dependency checks here (see /system/health for that).
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description=(
        "Returns 200 OK when the application process is alive. "
        "Does **not** check downstream dependencies."
    ),
)
async def health_check() -> HealthResponse:
    from app import __version__

    return HealthResponse(status="ok", version=__version__)
