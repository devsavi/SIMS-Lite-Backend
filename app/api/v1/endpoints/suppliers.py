"""
Supplier management endpoints.

GET    /api/v1/suppliers/       -- list
POST   /api/v1/suppliers/       -- create
GET    /api/v1/suppliers/{id}   -- get
PUT    /api/v1/suppliers/{id}   -- update
DELETE /api/v1/suppliers/{id}   -- soft delete
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.master_data import SupplierCreate, SupplierRead, SupplierUpdate
from app.services.master_data import SupplierService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> SupplierService:
    return SupplierService(db)


@router.get("/", response_model=PaginatedResponse[SupplierRead], summary="List suppliers")
async def list_suppliers(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    svc: SupplierService = Depends(_svc),
) -> PaginatedResponse[SupplierRead]:
    items, total = await svc.list(page=page, size=size, search=search, active_only=active_only)
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[SupplierRead.model_validate(s) for s in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.post("/", response_model=SuccessResponse[SupplierRead], status_code=status.HTTP_201_CREATED, summary="Create supplier")
async def create_supplier(
    payload: SupplierCreate,
    current_user: User = Depends(require_permission("master_data:write")),
    svc: SupplierService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[SupplierRead]:
    supplier = await svc.create(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=SupplierRead.model_validate(supplier))


@router.get("/{supplier_id}", response_model=SuccessResponse[SupplierRead], summary="Get supplier")
async def get_supplier(
    supplier_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: SupplierService = Depends(_svc),
) -> SuccessResponse[SupplierRead]:
    supplier = await svc.get(supplier_id)
    return SuccessResponse(data=SupplierRead.model_validate(supplier))


@router.put("/{supplier_id}", response_model=SuccessResponse[SupplierRead], summary="Update supplier")
async def update_supplier(
    supplier_id: uuid.UUID,
    payload: SupplierUpdate,
    current_user: User = Depends(require_permission("master_data:write")),
    svc: SupplierService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[SupplierRead]:
    supplier = await svc.update(supplier_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=SupplierRead.model_validate(supplier))


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete supplier")
async def delete_supplier(
    supplier_id: uuid.UUID,
    current_user: User = Depends(require_permission("master_data:delete")),
    svc: SupplierService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
):
    await svc.delete(supplier_id, actor=current_user, ip_address=ip)

