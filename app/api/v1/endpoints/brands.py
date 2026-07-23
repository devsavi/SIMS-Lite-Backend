"""
Brand management endpoints.

GET    /api/v1/brands/       -- list
POST   /api/v1/brands/       -- create
GET    /api/v1/brands/{id}   -- get
PUT    /api/v1/brands/{id}   -- update
DELETE /api/v1/brands/{id}   -- soft delete
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.master_data import BrandCreate, BrandRead, BrandUpdate
from app.services.master_data import BrandService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> BrandService:
    return BrandService(db)


@router.get("/", response_model=PaginatedResponse[BrandRead], summary="List brands")
async def list_brands(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    svc: BrandService = Depends(_svc),
) -> PaginatedResponse[BrandRead]:
    items, total = await svc.list(page=page, size=size, search=search, active_only=active_only)
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[BrandRead.model_validate(b) for b in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.post("/", response_model=SuccessResponse[BrandRead], status_code=status.HTTP_201_CREATED, summary="Create brand")
async def create_brand(
    payload: BrandCreate,
    current_user: User = Depends(require_permission("master_data:write")),
    svc: BrandService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[BrandRead]:
    brand = await svc.create(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=BrandRead.model_validate(brand))


@router.get("/{brand_id}", response_model=SuccessResponse[BrandRead], summary="Get brand")
async def get_brand(
    brand_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: BrandService = Depends(_svc),
) -> SuccessResponse[BrandRead]:
    brand = await svc.get(brand_id)
    return SuccessResponse(data=BrandRead.model_validate(brand))


@router.put("/{brand_id}", response_model=SuccessResponse[BrandRead], summary="Update brand")
async def update_brand(
    brand_id: uuid.UUID,
    payload: BrandUpdate,
    current_user: User = Depends(require_permission("master_data:write")),
    svc: BrandService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[BrandRead]:
    brand = await svc.update(brand_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=BrandRead.model_validate(brand))


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete brand")
async def delete_brand(
    brand_id: uuid.UUID,
    current_user: User = Depends(require_permission("master_data:delete")),
    svc: BrandService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
):
    await svc.delete(brand_id, actor=current_user, ip_address=ip)

