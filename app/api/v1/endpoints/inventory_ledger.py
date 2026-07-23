"""
Inventory Ledger endpoints — Phase 4.

GET /api/v1/inventory-ledger/                              — paginated ledger
GET /api/v1/inventory-ledger/{id}                         — single entry
GET /api/v1/inventory-ledger/product/{product_id}         — by product
GET /api/v1/inventory-ledger/reference/{ref_type}/{ref_id} — by reference doc
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.inventory import InventoryLedgerEntryRead, ProductInventoryRef, UserRef
from app.services.inventory import InventoryLedgerService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> InventoryLedgerService:
    return InventoryLedgerService(db)


def _to_read(entry) -> InventoryLedgerEntryRead:
    product_ref = None
    if entry.product:
        p = entry.product
        product_ref = ProductInventoryRef(
            id=p.id,
            sku=p.sku,
            name=p.name,
            barcode=p.barcode,
            reorder_level=p.reorder_level,
            cost_price=float(p.cost_price) if p.cost_price is not None else None,
            selling_price=float(p.selling_price) if p.selling_price is not None else None,
        )
    user_ref = None
    if entry.created_by:
        u = entry.created_by
        user_ref = UserRef(id=u.id, first_name=u.first_name, last_name=u.last_name, email=u.email)
    return InventoryLedgerEntryRead(
        id=entry.id,
        product=product_ref,
        entry_type=entry.entry_type,
        quantity_before=float(entry.quantity_before),
        quantity_change=float(entry.quantity_change),
        quantity_after=float(entry.quantity_after),
        unit_cost=float(entry.unit_cost),
        reference_type=entry.reference_type,
        reference_id=entry.reference_id,
        reference_number=entry.reference_number,
        notes=entry.notes,
        created_by=user_ref,
        created_at=entry.created_at,
    )


@router.get(
    "/",
    response_model=PaginatedResponse[InventoryLedgerEntryRead],
    summary="List inventory ledger entries",
)
async def list_ledger(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    product_id: uuid.UUID | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    reference_type: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryLedgerService = Depends(_svc),
) -> PaginatedResponse[InventoryLedgerEntryRead]:
    entries, total = await svc.get_all(
        page=page,
        size=size,
        product_id=product_id,
        entry_type=entry_type,
        reference_type=reference_type,
        from_date=from_date,
        to_date=to_date,
    )
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[_to_read(e) for e in entries],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.get(
    "/product/{product_id}",
    response_model=PaginatedResponse[InventoryLedgerEntryRead],
    summary="Get ledger history for a specific product",
)
async def get_ledger_by_product(
    product_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryLedgerService = Depends(_svc),
) -> PaginatedResponse[InventoryLedgerEntryRead]:
    entries, total = await svc.get_for_product(product_id, page=page, size=size)
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[_to_read(e) for e in entries],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.get(
    "/reference/{reference_type}/{reference_id}",
    response_model=SuccessResponse[list[InventoryLedgerEntryRead]],
    summary="Get ledger entries for a reference document (GRN, STOCK_ADJUSTMENT, etc.)",
)
async def get_ledger_by_reference(
    reference_type: str,
    reference_id: uuid.UUID,
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryLedgerService = Depends(_svc),
) -> SuccessResponse[list[InventoryLedgerEntryRead]]:
    entries = await svc.get_by_reference(reference_type.upper(), reference_id)
    return SuccessResponse(data=[_to_read(e) for e in entries])


@router.get(
    "/{entry_id}",
    response_model=SuccessResponse[InventoryLedgerEntryRead],
    summary="Get a single inventory ledger entry by ID",
)
async def get_ledger_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryLedgerService = Depends(_svc),
) -> SuccessResponse[InventoryLedgerEntryRead]:
    entry = await svc.get_by_id(entry_id)
    return SuccessResponse(data=_to_read(entry))
