"""
Stock Release endpoints — Phase 5.

GET    /api/v1/stock-releases/               — paginated list
POST   /api/v1/stock-releases/               — create draft release
GET    /api/v1/stock-releases/{id}           — get single release
PUT    /api/v1/stock-releases/{id}           — update draft
DELETE /api/v1/stock-releases/{id}           — soft-delete draft
PATCH  /api/v1/stock-releases/{id}/submit    — submit for approval
PATCH  /api/v1/stock-releases/{id}/approve   — approve (deducts inventory)
PATCH  /api/v1/stock-releases/{id}/cancel    — cancel
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
from app.schemas.stock_release import (
    CancelReleaseRequest,
    ProductReleaseRef,
    StockReleaseCreate,
    StockReleaseItemRead,
    StockReleaseRead,
    StockReleaseSummary,
    StockReleaseUpdate,
    UserReleaseRef,
)
from app.services.stock_release import StockReleaseService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> StockReleaseService:
    return StockReleaseService(db)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _user_ref(u) -> UserReleaseRef | None:
    if u is None:
        return None
    return UserReleaseRef(
        id=u.id,
        first_name=u.first_name,
        last_name=u.last_name,
        email=u.email,
    )


def _product_ref(p) -> ProductReleaseRef | None:
    if p is None:
        return None
    return ProductReleaseRef(
        id=p.id,
        sku=p.sku,
        name=p.name,
        barcode=p.barcode,
        reorder_level=p.reorder_level,
        cost_price=float(p.cost_price) if p.cost_price is not None else None,
        selling_price=float(p.selling_price) if p.selling_price is not None else None,
    )


def _to_read(sr) -> StockReleaseRead:
    items = [
        StockReleaseItemRead(
            id=item.id,
            stock_release_id=item.stock_release_id,
            product=_product_ref(item.product),
            quantity_requested=float(item.quantity_requested),
            unit_cost=float(item.unit_cost),
            line_total=float(item.line_total),
            notes=item.notes,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in sr.items
    ]
    return StockReleaseRead(
        id=sr.id,
        release_number=sr.release_number,
        purpose=sr.purpose,
        status=sr.status,
        release_date=sr.release_date,
        notes=sr.notes,
        reference_document=sr.reference_document,
        total_quantity=float(sr.total_quantity),
        total_cost=float(sr.total_cost),
        created_by=_user_ref(sr.created_by),
        submitted_by=_user_ref(sr.submitted_by),
        submitted_at=sr.submitted_at,
        approved_by=_user_ref(sr.approved_by),
        approved_at=sr.approved_at,
        cancelled_by=_user_ref(sr.cancelled_by),
        cancelled_at=sr.cancelled_at,
        cancellation_reason=sr.cancellation_reason,
        items=items,
        created_at=sr.created_at,
        updated_at=sr.updated_at,
    )


def _to_summary(sr) -> StockReleaseSummary:
    return StockReleaseSummary(
        id=sr.id,
        release_number=sr.release_number,
        purpose=sr.purpose,
        status=sr.status,
        release_date=sr.release_date,
        total_quantity=float(sr.total_quantity),
        total_cost=float(sr.total_cost),
        item_count=len(sr.items),
        created_by=_user_ref(sr.created_by),
        created_at=sr.created_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedResponse[StockReleaseSummary],
    summary="List stock releases",
)
async def list_stock_releases(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    search: str | None = Query(default=None, description="Search by release number"),
    status: str | None = Query(default=None),
    purpose: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_permission("inventory:read")),
    svc: StockReleaseService = Depends(_svc),
) -> PaginatedResponse[StockReleaseSummary]:
    items, total = await svc.get_all(
        page=page,
        size=size,
        search=search,
        status=status,
        purpose=purpose,
        from_date=from_date,
        to_date=to_date,
    )
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[_to_summary(sr) for sr in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.post(
    "/",
    response_model=SuccessResponse[StockReleaseRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new stock release (DRAFT)",
)
async def create_stock_release(
    payload: StockReleaseCreate,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockReleaseService = Depends(_svc),
) -> SuccessResponse[StockReleaseRead]:
    ip = get_client_ip(request)
    sr = await svc.create(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(sr))


@router.get(
    "/{release_id}",
    response_model=SuccessResponse[StockReleaseRead],
    summary="Get a stock release by ID",
)
async def get_stock_release(
    release_id: uuid.UUID,
    current_user: User = Depends(require_permission("inventory:read")),
    svc: StockReleaseService = Depends(_svc),
) -> SuccessResponse[StockReleaseRead]:
    sr = await svc.get(release_id)
    return SuccessResponse(data=_to_read(sr))


@router.put(
    "/{release_id}",
    response_model=SuccessResponse[StockReleaseRead],
    summary="Update a DRAFT stock release",
)
async def update_stock_release(
    release_id: uuid.UUID,
    payload: StockReleaseUpdate,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockReleaseService = Depends(_svc),
) -> SuccessResponse[StockReleaseRead]:
    ip = get_client_ip(request)
    sr = await svc.update(release_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(sr))


@router.delete(
    "/{release_id}",
    response_model=SuccessResponse[dict],
    summary="Delete a DRAFT stock release",
)
async def delete_stock_release(
    release_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockReleaseService = Depends(_svc),
) -> SuccessResponse[dict]:
    ip = get_client_ip(request)
    await svc.delete(release_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data={"deleted": True, "id": str(release_id)})


@router.patch(
    "/{release_id}/submit",
    response_model=SuccessResponse[StockReleaseRead],
    summary="Submit a stock release for approval",
)
async def submit_stock_release(
    release_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockReleaseService = Depends(_svc),
) -> SuccessResponse[StockReleaseRead]:
    ip = get_client_ip(request)
    sr = await svc.submit(release_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(sr))


@router.patch(
    "/{release_id}/approve",
    response_model=SuccessResponse[StockReleaseRead],
    summary="Approve a stock release (deducts inventory)",
)
async def approve_stock_release(
    release_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission("inventory:approve")),
    svc: StockReleaseService = Depends(_svc),
) -> SuccessResponse[StockReleaseRead]:
    ip = get_client_ip(request)
    sr = await svc.approve(release_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(sr))


@router.patch(
    "/{release_id}/cancel",
    response_model=SuccessResponse[StockReleaseRead],
    summary="Cancel a stock release (no inventory impact)",
)
async def cancel_stock_release(
    release_id: uuid.UUID,
    payload: CancelReleaseRequest,
    request: Request,
    current_user: User = Depends(require_permission("inventory:write")),
    svc: StockReleaseService = Depends(_svc),
) -> SuccessResponse[StockReleaseRead]:
    ip = get_client_ip(request)
    sr = await svc.cancel(
        release_id, payload.reason, actor=current_user, ip_address=ip
    )
    return SuccessResponse(data=_to_read(sr))
