"""
Purchase Order endpoints — Phase 3.

GET    /api/v1/purchase-orders/
POST   /api/v1/purchase-orders/
GET    /api/v1/purchase-orders/{id}
PUT    /api/v1/purchase-orders/{id}
DELETE /api/v1/purchase-orders/{id}
PATCH  /api/v1/purchase-orders/{id}/submit
PATCH  /api/v1/purchase-orders/{id}/approve
PATCH  /api/v1/purchase-orders/{id}/reject
PATCH  /api/v1/purchase-orders/{id}/cancel
POST   /api/v1/purchase-orders/{id}/duplicate
GET    /api/v1/purchase-orders/{id}/print
POST   /api/v1/purchase-orders/{id}/email
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
    EmailPORequest,
    POItemRead,
    PurchaseOrderCreate,
    PurchaseOrderRead,
    PurchaseOrderSummary,
    PurchaseOrderUpdate,
    RejectPORequest,
)
from app.services.procurement import PurchaseOrderService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> PurchaseOrderService:
    return PurchaseOrderService(db)


def _to_summary(po) -> PurchaseOrderSummary:
    from app.schemas.procurement import SupplierRef

    supplier_ref = None
    if po.supplier:
        supplier_ref = SupplierRef(
            id=po.supplier.id,
            supplier_code=po.supplier.supplier_code,
            name=po.supplier.name,
            email=po.supplier.email,
            contact_person=po.supplier.contact_person,
        )
    return PurchaseOrderSummary(
        id=po.id,
        po_number=po.po_number,
        supplier=supplier_ref,
        status=po.status,
        order_date=po.order_date,
        expected_delivery_date=po.expected_delivery_date,
        total_amount=float(po.total_amount),
        item_count=len(po.items),
        created_at=po.created_at,
    )


def _to_read(po) -> PurchaseOrderRead:
    from app.schemas.procurement import ProductRef, SupplierRef, UserRef

    def _user_ref(u) -> UserRef | None:
        if u is None:
            return None
        return UserRef(id=u.id, first_name=u.first_name, last_name=u.last_name, email=u.email)

    supplier_ref = None
    if po.supplier:
        supplier_ref = SupplierRef(
            id=po.supplier.id,
            supplier_code=po.supplier.supplier_code,
            name=po.supplier.name,
            email=po.supplier.email,
            contact_person=po.supplier.contact_person,
        )

    items = []
    for item in po.items:
        product_ref = None
        if item.product:
            product_ref = ProductRef(
                id=item.product.id,
                sku=item.product.sku,
                name=item.product.name,
                barcode=item.product.barcode,
            )
        items.append(
            POItemRead(
                id=item.id,
                purchase_order_id=item.purchase_order_id,
                product=product_ref,
                quantity_ordered=float(item.quantity_ordered),
                unit_price=float(item.unit_price),
                discount_percent=float(item.discount_percent),
                tax_percent=float(item.tax_percent),
                line_total=float(item.line_total),
                quantity_received=float(item.quantity_received),
                notes=item.notes,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    return PurchaseOrderRead(
        id=po.id,
        po_number=po.po_number,
        supplier=supplier_ref,
        status=po.status,
        order_date=po.order_date,
        expected_delivery_date=po.expected_delivery_date,
        subtotal=float(po.subtotal),
        tax_amount=float(po.tax_amount),
        discount_amount=float(po.discount_amount),
        total_amount=float(po.total_amount),
        notes=po.notes,
        terms_conditions=po.terms_conditions,
        shipping_address=po.shipping_address,
        created_by=_user_ref(po.created_by),
        submitted_by=_user_ref(po.submitted_by),
        submitted_at=po.submitted_at,
        approved_by=_user_ref(po.approved_by),
        approved_at=po.approved_at,
        rejected_by=_user_ref(po.rejected_by),
        rejected_at=po.rejected_at,
        rejection_reason=po.rejection_reason,
        cancelled_by=_user_ref(po.cancelled_by),
        cancelled_at=po.cancelled_at,
        cancellation_reason=po.cancellation_reason,
        email_sent_at=po.email_sent_at,
        email_sent_to=po.email_sent_to,
        items=items,
        created_at=po.created_at,
        updated_at=po.updated_at,
    )


# ---------------------------------------------------------------------------
# List / Create
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedResponse[PurchaseOrderSummary],
    summary="List purchase orders",
)
async def list_purchase_orders(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    supplier_id: uuid.UUID | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    svc: PurchaseOrderService = Depends(_svc),
) -> PaginatedResponse[PurchaseOrderSummary]:
    items, total = await svc.list(
        page=page,
        size=size,
        search=search,
        status=status,
        supplier_id=supplier_id,
        from_date=from_date,
        to_date=to_date,
    )
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=[_to_summary(po) for po in items],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.post(
    "/",
    response_model=SuccessResponse[PurchaseOrderRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create purchase order",
)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: PurchaseOrderService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[PurchaseOrderRead]:
    po = await svc.create(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(po))


# ---------------------------------------------------------------------------
# Get / Update / Delete
# ---------------------------------------------------------------------------


@router.get(
    "/{po_id}",
    response_model=SuccessResponse[PurchaseOrderRead],
    summary="Get purchase order",
)
async def get_purchase_order(
    po_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: PurchaseOrderService = Depends(_svc),
) -> SuccessResponse[PurchaseOrderRead]:
    po = await svc.get(po_id)
    return SuccessResponse(data=_to_read(po))


@router.put(
    "/{po_id}",
    response_model=SuccessResponse[PurchaseOrderRead],
    summary="Update purchase order (DRAFT only)",
)
async def update_purchase_order(
    po_id: uuid.UUID,
    payload: PurchaseOrderUpdate,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: PurchaseOrderService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[PurchaseOrderRead]:
    po = await svc.update(po_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(po))


@router.delete(
    "/{po_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete purchase order (DRAFT only)",
)
async def delete_purchase_order(
    po_id: uuid.UUID,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: PurchaseOrderService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
):
    await svc.delete(po_id, actor=current_user, ip_address=ip)


# ---------------------------------------------------------------------------
# Workflow transitions
# ---------------------------------------------------------------------------


@router.patch(
    "/{po_id}/submit",
    response_model=SuccessResponse[PurchaseOrderRead],
    summary="Submit purchase order for approval",
)
async def submit_purchase_order(
    po_id: uuid.UUID,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: PurchaseOrderService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[PurchaseOrderRead]:
    po = await svc.submit(po_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(po))


@router.patch(
    "/{po_id}/approve",
    response_model=SuccessResponse[PurchaseOrderRead],
    summary="Approve a submitted purchase order",
)
async def approve_purchase_order(
    po_id: uuid.UUID,
    current_user: User = Depends(require_permission("procurement:approve")),
    svc: PurchaseOrderService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[PurchaseOrderRead]:
    po = await svc.approve(po_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(po))


@router.patch(
    "/{po_id}/reject",
    response_model=SuccessResponse[PurchaseOrderRead],
    summary="Reject a submitted purchase order",
)
async def reject_purchase_order(
    po_id: uuid.UUID,
    payload: RejectPORequest,
    current_user: User = Depends(require_permission("procurement:approve")),
    svc: PurchaseOrderService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[PurchaseOrderRead]:
    po = await svc.reject(po_id, payload.reason, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(po))


@router.patch(
    "/{po_id}/cancel",
    response_model=SuccessResponse[PurchaseOrderRead],
    summary="Cancel a draft or submitted purchase order",
)
async def cancel_purchase_order(
    po_id: uuid.UUID,
    payload: CancelRequest,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: PurchaseOrderService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[PurchaseOrderRead]:
    po = await svc.cancel(po_id, payload.reason, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(po))


# ---------------------------------------------------------------------------
# Special actions
# ---------------------------------------------------------------------------


@router.post(
    "/{po_id}/duplicate",
    response_model=SuccessResponse[PurchaseOrderRead],
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a purchase order as a new DRAFT",
)
async def duplicate_purchase_order(
    po_id: uuid.UUID,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: PurchaseOrderService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[PurchaseOrderRead]:
    po = await svc.duplicate(po_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=_to_read(po))


@router.get(
    "/{po_id}/print",
    response_model=SuccessResponse[dict],
    summary="Get purchase order print data",
)
async def print_purchase_order(
    po_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: PurchaseOrderService = Depends(_svc),
) -> SuccessResponse[dict]:
    data = await svc.get_for_print(po_id)
    return SuccessResponse(data=data)


@router.post(
    "/{po_id}/email",
    response_model=SuccessResponse[PurchaseOrderRead],
    summary="Email purchase order to supplier",
)
async def email_purchase_order(
    po_id: uuid.UUID,
    payload: EmailPORequest,
    current_user: User = Depends(require_permission("procurement:write")),
    svc: PurchaseOrderService = Depends(_svc),
    ip: str | None = Depends(get_client_ip),
) -> SuccessResponse[PurchaseOrderRead]:
    po = await svc.send_email(
        po_id,
        to_email=payload.to_email,
        message=payload.message,
        actor=current_user,
        ip_address=ip,
    )
    return SuccessResponse(data=_to_read(po))
