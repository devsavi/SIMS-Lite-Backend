"""
Category management endpoints.

GET    /api/v1/categories/          -- list (paginated, search, filter)
POST   /api/v1/categories/          -- create
GET    /api/v1/categories/{id}      -- get by id
PUT    /api/v1/categories/{id}      -- update
DELETE /api/v1/categories/{id}      -- soft delete
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.master_data import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.master_data import CategoryService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> CategoryService:
    return CategoryService(db)


@router.get("/", response_model=PaginatedResponse[CategoryRead], summary="List categories")
async def list_categories(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    parent_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    svc: CategoryService = Depends(_svc),
) -> PaginatedResponse[CategoryRead]:
    items, total = await svc.list(
        page=page, size=size, search=search,
        active_only=active_only,
        parent_id=parent_id,
        include_parent_filter=parent_id is not None,
    )
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[CategoryRead.model_validate(c) for c in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.post("/", response_model=SuccessResponse[CategoryRead], status_code=status.HTTP_201_CREATED, summary="Create category")
async def create_category(
    payload: CategoryCreate,
    request: Request,
    current_user: User = Depends(require_permission("master_data:write")),
    svc: CategoryService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[CategoryRead]:
    cat = await svc.create(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=CategoryRead.model_validate(cat))


@router.get("/{category_id}", response_model=SuccessResponse[CategoryRead], summary="Get category")
async def get_category(
    category_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: CategoryService = Depends(_svc),
) -> SuccessResponse[CategoryRead]:
    cat = await svc.get(category_id)
    return SuccessResponse(data=CategoryRead.model_validate(cat))


@router.put("/{category_id}", response_model=SuccessResponse[CategoryRead], summary="Update category")
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    current_user: User = Depends(require_permission("master_data:write")),
    svc: CategoryService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[CategoryRead]:
    cat = await svc.update(category_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=CategoryRead.model_validate(cat))


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete category")
async def delete_category(
    category_id: uuid.UUID,
    current_user: User = Depends(require_permission("master_data:delete")),
    svc: CategoryService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
):
    await svc.delete(category_id, actor=current_user, ip_address=ip)

