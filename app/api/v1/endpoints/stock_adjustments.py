"""
Stock Adjustment endpoints — Phase 4.

GET    /api/v1/stock-adjustments/               — paginated list
POST   /api/v1/stock-adjustments/               — create draft adjustment
GET    /api/v1/stock-adjustments/{id}           — get single adjustment
PUT    /api/v1/stock-adjustments/{id}           — update draft
DELETE /api/v1/stock-adjustments/{id}           — soft-delete draft
PATCH  /api/v1/stock-adjustments/{id}/submit    — submit for approval
PATCH  /api/v1/stock-adjustments/{id}/approve   — approve (applies to inventory)
PATCH  /api/v1/stock-adjustments/{id}/cancel    — cancel
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.inventory import (
    CancelAdjustmentRequest,
    ProductInventoryRef,
    StockAdjustmentCreate,
    StockAdjustmentItemRead,
    StockAdjustmentRead,
    StockAdjustmentSummary,
    StockAdjustmentUpdate,
    UserRef,
)
from app.services.inventory import StockAdjustmentService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> StockAdjustmentService:
    return StockAdjustmentService(db)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _user_ref(u) -> UserRef | None:
    if u is None:
        return None
    return UserRef(id=u.id, first_name=u.first_name, last_name=u.last_name, email=u.email)


def _product_ref(p) -> ProductInventoryRef | None:
    if p is None:
        return None
    return ProductInventoryRef(
        id=p.id,
        sku=p.sku,
        name=p.name,
        barcode=p.barcode,
        reorder_level=p.reorder_level,
        cost_price=float(p.cost_price) if p.cost_price is not None else None,
        selling_price=float(p.selling_price) if p.selling_price is not None else None,
    )


def _to_read(adj) -> StockAdjustmentRead:
    items = []
    for item in adj.items:
        items.append(
            StockAdjustmentItemRead(
                id=item.id,
                stock_adjustment_id=item.stock_adjustment_id,
                product=_product_ref(item.product),
                quantity_adjusted=float(item.quantity_adjusted),
                unit_cost=float(item.unit_cost),
                notes=item.notes,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
    return StockAdjustmentRead(
        id=adj.id,
        adjustment_number=adj.adjustment_number,
        adjustment_type=adj.adjustment_type,
        status=adj.status,
        reason=adj.reason,
        notes=adj.notes,
        created_by=_user_ref(adj.created_by),
        submitted_by=_user_ref(adj.submitted_by),
        submitted_at=adj.submitted_at,
        approved_by=_user_ref(adj.approved_by),
        approved_at=adj.approved_at,
        cancelled_by=_user_ref(adj.cancelled_by),
        cancelled_at=adj.cancelled_at,
        cancellation_reason=adj.cancellation_reason,
        items=items,
        created_at=adj.created_at,
        updated_at=adj.updated_at,
    )


def _to_summary(adj) -> StockAdjustmentSummary:
    return StockAdjustmentSummary(
        id=adj.id,
        adjustment_number=adj.adjustment_number,
        adjustment_type=adj.adjustment_type,
        status=adj.status,
        reason=adj.reason,
        item_count=len(adj.items),
        created_by=_user_ref(adj.created_by),
        created_at=adj.created_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedResponse[StockAdjustmentSummary],
    summary="List stock adjustments",
)
async def list_adjustments(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    adjustment_type: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_permission("inventory:read")),
    svc: StockAdjustmentService = Depends(_svc),
) -> PaginatedResponse[StockAdjustmentSummary]:
    items, total = await svc.get_all(
        page=page,
        size=size,
        search=search,
        status=status,
        adjustment_type=adjustment_type,
        from_date=from_date,
        to_date=to_date,
    )
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[_to_summary(adj) for adj in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.post(
    "/",
    response_model=SuccessResponse[StockAdjustmentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new stock adjustment (DRAFT)",
)
async def create_adjustment(
    payload: StockAdjustmentCreate,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockAdjustmentService = Depends(_svc),
) -> SuccessResponse[StockAdjustmentRead]:
    ip = get_client_ip(request)
    adj = await svc.create(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(adj))


@router.get(
    "/{adjustment_id}",
    response_model=SuccessResponse[StockAdjustmentRead],
    summary="Get a stock adjustment by ID",
)
async def get_adjustment(
    adjustment_id: uuid.UUID,
    current_user: User = Depends(require_permission("inventory:read")),
    svc: StockAdjustmentService = Depends(_svc),
) -> SuccessResponse[StockAdjustmentRead]:
    adj = await svc.get(adjustment_id)
    return SuccessResponse(data=_to_read(adj))


@router.put(
    "/{adjustment_id}",
    response_model=SuccessResponse[StockAdjustmentRead],
    summary="Update a DRAFT stock adjustment",
)
async def update_adjustment(
    adjustment_id: uuid.UUID,
    payload: StockAdjustmentUpdate,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockAdjustmentService = Depends(_svc),
) -> SuccessResponse[StockAdjustmentRead]:
    ip = get_client_ip(request)
    adj = await svc.update(adjustment_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(adj))


@router.delete(
    "/{adjustment_id}",
    response_model=SuccessResponse[dict],
    summary="Delete a DRAFT stock adjustment",
)
async def delete_adjustment(
    adjustment_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockAdjustmentService = Depends(_svc),
) -> SuccessResponse[dict]:
    ip = get_client_ip(request)
    await svc.delete(adjustment_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data={"deleted": True, "id": str(adjustment_id)})


@router.patch(
    "/{adjustment_id}/submit",
    response_model=SuccessResponse[StockAdjustmentRead],
    summary="Submit a stock adjustment for approval",
)
async def submit_adjustment(
    adjustment_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockAdjustmentService = Depends(_svc),
) -> SuccessResponse[StockAdjustmentRead]:
    ip = get_client_ip(request)
    adj = await svc.submit(adjustment_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(adj))


@router.patch(
    "/{adjustment_id}/approve",
    response_model=SuccessResponse[StockAdjustmentRead],
    summary="Approve a stock adjustment (applies inventory changes)",
)
async def approve_adjustment(
    adjustment_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockAdjustmentService = Depends(_svc),
) -> SuccessResponse[StockAdjustmentRead]:
    ip = get_client_ip(request)
    adj = await svc.approve(adjustment_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(adj))


@router.patch(
    "/{adjustment_id}/cancel",
    response_model=SuccessResponse[StockAdjustmentRead],
    summary="Cancel a stock adjustment",
)
async def cancel_adjustment(
    adjustment_id: uuid.UUID,
    payload: CancelAdjustmentRequest,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockAdjustmentService = Depends(_svc),
) -> SuccessResponse[StockAdjustmentRead]:
    ip = get_client_ip(request)
    adj = await svc.cancel(
        adjustment_id, payload.reason, actor=current_user, ip_address=ip
    )
    return SuccessResponse(data=_to_read(adj))
