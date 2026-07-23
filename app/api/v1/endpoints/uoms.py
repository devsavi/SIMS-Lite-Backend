"""
Unit of Measure endpoints.

GET    /api/v1/uoms/       -- list
POST   /api/v1/uoms/       -- create
GET    /api/v1/uoms/{id}   -- get
PUT    /api/v1/uoms/{id}   -- update
DELETE /api/v1/uoms/{id}   -- soft delete
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.master_data import UoMCreate, UoMRead, UoMUpdate
from app.services.master_data import UoMService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> UoMService:
    return UoMService(db)


@router.get("/", response_model=PaginatedResponse[UoMRead], summary="List units of measure")
async def list_uoms(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    svc: UoMService = Depends(_svc),
) -> PaginatedResponse[UoMRead]:
    items, total = await svc.list(page=page, size=size, search=search, active_only=active_only)
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[UoMRead.model_validate(u) for u in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.post("/", response_model=SuccessResponse[UoMRead], status_code=status.HTTP_201_CREATED, summary="Create unit of measure")
async def create_uom(
    payload: UoMCreate,
    current_user: User = Depends(require_permission("master_data:write")),
    svc: UoMService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[UoMRead]:
    uom = await svc.create(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=UoMRead.model_validate(uom))


@router.get("/{uom_id}", response_model=SuccessResponse[UoMRead], summary="Get unit of measure")
async def get_uom(
    uom_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: UoMService = Depends(_svc),
) -> SuccessResponse[UoMRead]:
    uom = await svc.get(uom_id)
    return SuccessResponse(data=UoMRead.model_validate(uom))


@router.put("/{uom_id}", response_model=SuccessResponse[UoMRead], summary="Update unit of measure")
async def update_uom(
    uom_id: uuid.UUID,
    payload: UoMUpdate,
    current_user: User = Depends(require_permission("master_data:write")),
    svc: UoMService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[UoMRead]:
    uom = await svc.update(uom_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=UoMRead.model_validate(uom))


@router.delete("/{uom_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete unit of measure")
async def delete_uom(
    uom_id: uuid.UUID,
    current_user: User = Depends(require_permission("master_data:delete")),
    svc: UoMService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
):
    await svc.delete(uom_id, actor=current_user, ip_address=ip)

