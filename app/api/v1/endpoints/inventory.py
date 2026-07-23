"""
Inventory endpoints — Phase 4.

GET    /api/v1/inventory/                           — paginated current stock list
GET    /api/v1/inventory/summary                    — aggregate summary
GET    /api/v1/inventory/value                      — inventory valuation
GET    /api/v1/inventory/low-stock                  — products at/below reorder level
GET    /api/v1/inventory/out-of-stock               — products with zero stock
GET    /api/v1/inventory/{product_id}               — single product stock
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.inventory import (
    InventoryDashboard,
    InventoryRead,
    InventorySummary,
    InventoryValuation,
    InventoryValuationSummary,
    ProductInventoryRef,
)
from app.services.inventory import InventoryService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> InventoryService:
    return InventoryService(db)


def _to_read(inv) -> InventoryRead:
    product_ref = None
    if inv.product:
        p = inv.product
        product_ref = ProductInventoryRef(
            id=p.id,
            sku=p.sku,
            name=p.name,
            barcode=p.barcode,
            reorder_level=p.reorder_level,
            cost_price=float(p.cost_price) if p.cost_price is not None else None,
            selling_price=float(p.selling_price) if p.selling_price is not None else None,
        )
    qty = float(inv.quantity_on_hand)
    avg = float(inv.average_cost)
    return InventoryRead(
        id=inv.id,
        product=product_ref,
        quantity_on_hand=qty,
        average_cost=avg,
        stock_value=round(qty * avg, 4),
        last_updated_at=inv.last_updated_at,
        last_transaction_type=inv.last_transaction_type,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
    )


@router.get(
    "/summary",
    response_model=SuccessResponse[InventorySummary],
    summary="Inventory aggregate summary",
)
async def get_inventory_summary(
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryService = Depends(_svc),
) -> SuccessResponse[InventorySummary]:
    data = await svc.get_summary()
    return SuccessResponse(data=InventorySummary(**data))


@router.get(
    "/value",
    response_model=SuccessResponse[InventoryValuationSummary],
    summary="Inventory valuation (stock value by product)",
)
async def get_inventory_valuation(
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryService = Depends(_svc),
) -> SuccessResponse[InventoryValuationSummary]:
    items = await svc.get_valuation()
    valuations = []
    total_qty = 0.0
    total_value = 0.0
    for inv in items:
        p = inv.product
        qty = float(inv.quantity_on_hand)
        avg = float(inv.average_cost)
        val = round(qty * avg, 4)
        total_qty += qty
        total_value += val
        valuations.append(
            InventoryValuation(
                product_id=inv.product_id,
                sku=p.sku if p else "",
                product_name=p.name if p else "",
                quantity_on_hand=qty,
                average_cost=avg,
                stock_value=val,
            )
        )
    return SuccessResponse(
        data=InventoryValuationSummary(
            total_products=len(valuations),
            total_quantity=round(total_qty, 4),
            total_value=round(total_value, 4),
            items=valuations,
        )
    )


@router.get(
    "/low-stock",
    response_model=PaginatedResponse[InventoryRead],
    summary="Products at or below reorder level",
)
async def get_low_stock(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryService = Depends(_svc),
) -> PaginatedResponse[InventoryRead]:
    items, total = await svc.get_low_stock(page=page, size=size)
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[_to_read(inv) for inv in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.get(
    "/out-of-stock",
    response_model=PaginatedResponse[InventoryRead],
    summary="Products with zero stock",
)
async def get_out_of_stock(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryService = Depends(_svc),
) -> PaginatedResponse[InventoryRead]:
    items, total = await svc.get_out_of_stock(page=page, size=size)
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[_to_read(inv) for inv in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.get(
    "/{product_id}",
    response_model=SuccessResponse[InventoryRead],
    summary="Get current stock for a specific product",
)
async def get_inventory_by_product(
    product_id: uuid.UUID,
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryService = Depends(_svc),
) -> SuccessResponse[InventoryRead]:
    inv = await svc.get_by_product(product_id)
    return SuccessResponse(data=_to_read(inv))


@router.get(
    "/",
    response_model=PaginatedResponse[InventoryRead],
    summary="List current stock for all products",
)
async def list_inventory(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None, description="Search by name, SKU, or barcode"),
    category_id: uuid.UUID | None = Query(default=None),
    supplier_id: uuid.UUID | None = Query(default=None),
    low_stock_only: bool = Query(default=False),
    out_of_stock_only: bool = Query(default=False),
    current_user: User = Depends(require_permission("inventory:read")),
    svc: InventoryService = Depends(_svc),
) -> PaginatedResponse[InventoryRead]:
    items, total = await svc.get_all(
        page=page,
        size=size,
        search=search,
        category_id=category_id,
        supplier_id=supplier_id,
        low_stock_only=low_stock_only,
        out_of_stock_only=out_of_stock_only,
    )
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[_to_read(inv) for inv in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )
