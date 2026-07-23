"""
Inventory endpoints — Phase 3.

GET /api/v1/inventory/{product_id}/stock    -- current stock level
GET /api/v1/inventory/{product_id}/ledger   -- paginated ledger history
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.procurement import InventoryLedgerRead
from app.services.procurement import InventoryLedgerService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> InventoryLedgerService:
    return InventoryLedgerService(db)


@router.get(
    "/{product_id}/stock",
    response_model=SuccessResponse[dict],
    summary="Get current stock level for a product",
)
async def get_stock(
    product_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: InventoryLedgerService = Depends(_svc),
) -> SuccessResponse[dict]:
    qty = await svc.get_current_stock(product_id)
    return SuccessResponse(data={"product_id": str(product_id), "quantity": qty})


@router.get(
    "/{product_id}/ledger",
    response_model=PaginatedResponse[InventoryLedgerRead],
    summary="Get inventory ledger history for a product",
)
async def get_ledger(
    product_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    svc: InventoryLedgerService = Depends(_svc),
) -> PaginatedResponse[InventoryLedgerRead]:
    entries, total = await svc.get_for_product(product_id, page=page, size=size)
    pages = (total + size - 1) // size if total else 0

    data = []
    for e in entries:
        product_ref = None
        if e.product:
            from app.schemas.procurement import ProductRef
            product_ref = ProductRef(
                id=e.product.id,
                sku=e.product.sku,
                name=e.product.name,
                barcode=e.product.barcode,
            )
        data.append(
            InventoryLedgerRead(
                id=e.id,
                product=product_ref,
                entry_type=e.entry_type,
                quantity_before=float(e.quantity_before),
                quantity_change=float(e.quantity_change),
                quantity_after=float(e.quantity_after),
                unit_cost=float(e.unit_cost),
                grn_id=e.grn_id,
                reference_number=e.reference_number,
                notes=e.notes,
                created_at=e.created_at,
            )
        )

    return PaginatedResponse(
        data=data,
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )
