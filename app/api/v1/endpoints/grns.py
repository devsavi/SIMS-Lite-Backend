"""
GRN (Goods Received Note) endpoints — Phase 3.

GET    /api/v1/grns/
POST   /api/v1/grns/
GET    /api/v1/grns/{id}
PUT    /api/v1/grns/{id}
PATCH  /api/v1/grns/{id}/submit
PATCH  /api/v1/grns/{id}/approve
PATCH  /api/v1/grns/{id}/cancel
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.procurement import (
    CancelRequest,
    GRNCreate,
    GRNItemRead,
    GRNRead,
    GRNUpdate,
)
from app.services.procurement import GRNService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> GRNService:
    return GRNService(db)


def _to_read(grn) -> GRNRead:
    from app.schemas.procurement import ProductRef, SupplierRef, UserRef

    def _user_ref(u) -> UserRef | None:
        if u is None:
            return None
        return UserRef(id=u.id, first_name=u.first_name, last_name=u.last_name, email=u.email)

    supplier_ref = None
    po_number = None
    if grn.purchase_order:
        po_number = grn.purchase_order.po_number
        if grn.purchase_order.supplier:
            s = grn.purchase_order.supplier
            supplier_ref = SupplierRef(
                id=s.id,
                supplier_code=s.supplier_code,
                name=s.name,
                email=s.email,
                contact_person=s.contact_person,
            )

    items = []
    for item in grn.items:
        product_ref = None
        if item.product:
            product_ref = ProductRef(
                id=item.product.id,
                sku=item.product.sku,
                name=item.product.name,
                barcode=item.product.barcode,
            )
        items.append(
            GRNItemRead(
                id=item.id,
                grn_id=item.grn_id,
                po_item_id=item.po_item_id,
                product=product_ref,
                quantity_received=float(item.quantity_received),
                unit_cost=float(item.unit_cost),
                notes=item.notes,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    return GRNRead(
        id=grn.id,
        grn_number=grn.grn_number,
        purchase_order_id=grn.purchase_order_id,
        po_number=po_number,
        supplier=supplier_ref,
        status=grn.status,
        received_date=grn.received_date,
        delivery_note_number=grn.delivery_note_number,
        notes=grn.notes,
        created_by=_user_ref(grn.created_by),
        submitted_by=_user_ref(grn.submitted_by),
        submitted_at=grn.submitted_at,
        approved_by=_user_ref(grn.approved_by),
        approved_at=grn.approved_at,
        cancelled_by=_user_ref(grn.cancelled_by),
        cancelled_at=grn.cancelled_at,
        cancellation_reason=grn.cancellation_reason,
        items=items,
        created_at=grn.created_at,
        updated_at=grn.updated_at,
    )


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedResponse[GRNRead],
    summary="List GRNs",
)
async def list_grns(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    po_id: uuid.UUID | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    svc: GRNService = Depends(_svc),
) -> PaginatedResponse[GRNRead]:
    items, total = await svc.list(
        page=page,
        size=size,
        search=search,
        status=status,
        po_id=po_id,
        from_date=from_date,
        to_date=to_date,
    )
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[_to_read(g) for g in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.post(
    "/",
    response_model=SuccessResponse[GRNRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create GRN",
)
async def create_grn(
    payload: GRNCreate,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: GRNService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[GRNRead]:
    grn = await svc.create(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(grn))


# ---------------------------------------------------------------------------
# Get / Update
# ---------------------------------------------------------------------------


@router.get(
    "/{grn_id}",
    response_model=SuccessResponse[GRNRead],
    summary="Get GRN",
)
async def get_grn(
    grn_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: GRNService = Depends(_svc),
) -> SuccessResponse[GRNRead]:
    grn = await svc.get(grn_id)
    return SuccessResponse(data=_to_read(grn))


@router.put(
    "/{grn_id}",
    response_model=SuccessResponse[GRNRead],
    summary="Update GRN (DRAFT only)",
)
async def update_grn(
    grn_id: uuid.UUID,
    payload: GRNUpdate,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: GRNService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[GRNRead]:
    grn = await svc.update(grn_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(grn))


# ---------------------------------------------------------------------------
# Workflow transitions
# ---------------------------------------------------------------------------


@router.patch(
    "/{grn_id}/submit",
    response_model=SuccessResponse[GRNRead],
    summary="Submit GRN for approval",
)
async def submit_grn(
    grn_id: uuid.UUID,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: GRNService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[GRNRead]:
    grn = await svc.submit(grn_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(grn))


@router.patch(
    "/{grn_id}/approve",
    response_model=SuccessResponse[GRNRead],
    summary="Approve GRN and post inventory",
)
async def approve_grn(
    grn_id: uuid.UUID,
    current_user: User = Depends(require_permission("procurement:approve")),
    svc: GRNService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[GRNRead]:
    grn = await svc.approve(grn_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(grn))


@router.patch(
    "/{grn_id}/cancel",
    response_model=SuccessResponse[GRNRead],
    summary="Cancel GRN",
)
async def cancel_grn(
    grn_id: uuid.UUID,
    payload: CancelRequest,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: GRNService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[GRNRead]:
    grn = await svc.cancel(grn_id, payload.reason, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(grn))
