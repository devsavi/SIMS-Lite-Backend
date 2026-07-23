from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.procurement import (
    GRN,
    GRNItem,
    GRNStatus,
    InventoryLedger,
    LedgerEntryType,
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.models.user import User
from app.repositories.audit_log import AuditLogRepository
from app.repositories.master_data import ProductRepository, SupplierRepository
from app.repositories.procurement import (
    GRNRepository,
    InventoryLedgerRepository,
    PurchaseOrderRepository,
)
from sqlalchemy import update as _sa_update

from app.schemas.procurement import (
    GRNCreate,
    GRNUpdate,
    POItemCreate,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)
from app.services.email import EmailService
from app.websockets.events import make_event
from app.websockets.manager import ws_manager

logger = get_logger(__name__)

_EDITABLE_STATUSES = {POStatus.DRAFT}
_SUBMITTABLE_STATUSES = {POStatus.DRAFT}
_APPROVABLE_STATUSES = {POStatus.SUBMITTED}
_REJECTABLE_STATUSES = {POStatus.SUBMITTED}
_CANCELLABLE_PO_STATUSES = {POStatus.DRAFT, POStatus.SUBMITTED}
_GRN_ALLOWED_PO_STATUSES = {POStatus.APPROVED, POStatus.PARTIALLY_RECEIVED}


def _calc_line_total(qty: float, unit_price: float, discount_pct: float, tax_pct: float) -> float:
    base = float(qty) * float(unit_price)
    disc = base * float(discount_pct) / 100
    net = base - disc
    tax = net * float(tax_pct) / 100
    return round(net + tax, 4)


def _recalc_po_totals(po: PurchaseOrder) -> None:
    subtotal = 0.0
    tax_total = 0.0
    discount_total = 0.0
    for item in po.items:
        base = float(item.quantity_ordered) * float(item.unit_price)
        disc = base * float(item.discount_percent) / 100
        net = base - disc
        tax = net * float(item.tax_percent) / 100
        subtotal += base
        discount_total += disc
        tax_total += tax
    po.subtotal = round(subtotal, 4)
    po.discount_amount = round(discount_total, 4)
    po.tax_amount = round(tax_total, 4)
    po.total_amount = round(subtotal - discount_total + tax_total, 4)


class PurchaseOrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._pos = PurchaseOrderRepository(session)
        self._suppliers = SupplierRepository(session)
        self._products = ProductRepository(session)
        self._audit = AuditLogRepository(session)

    async def create(
        self,
        payload: PurchaseOrderCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> PurchaseOrder:
        supplier = await self._suppliers.get_active(payload.supplier_id)
        if not supplier:
            raise NotFoundError("Supplier not found.")

        for item_payload in payload.items:
            product = await self._products.get_active(item_payload.product_id)
            if not product:
                raise NotFoundError(f"Product {item_payload.product_id} not found.")

        po_number = await self._pos.get_next_po_number()
        while await self._pos.po_number_exists(po_number):
            po_number = await self._pos.get_next_po_number()

        po = await self._pos.create(
            po_number=po_number,
            supplier_id=payload.supplier_id,
            status=POStatus.DRAFT,
            order_date=payload.order_date,
            expected_delivery_date=payload.expected_delivery_date,
            notes=payload.notes,
            terms_conditions=payload.terms_conditions,
            shipping_address=payload.shipping_address,
            created_by_id=actor.id,
            subtotal=0,
            tax_amount=0,
            discount_amount=0,
            total_amount=0,
        )

        for item_payload in payload.items:
            line_total = _calc_line_total(
                item_payload.quantity_ordered,
                item_payload.unit_price,
                item_payload.discount_percent,
                item_payload.tax_percent,
            )
            item = PurchaseOrderItem(
                purchase_order_id=po.id,
                product_id=item_payload.product_id,
                quantity_ordered=item_payload.quantity_ordered,
                unit_price=item_payload.unit_price,
                discount_percent=item_payload.discount_percent,
                tax_percent=item_payload.tax_percent,
                line_total=line_total,
                quantity_received=0,
                notes=item_payload.notes,
            )
            self._session.add(item)

        await self._session.flush()
        po = await self._pos.get_active(po.id)
        _recalc_po_totals(po)
        await self._session.flush()
        await self._session.refresh(po)
        po = await self._pos.get_active(po.id)

        await self._audit.log(
            actor_id=actor.id,
            action="po:create",
            resource_type="purchase_orders",
            resource_id=str(po.id),
            ip_address=ip_address,
            status="success",
            detail={"po_number": po.po_number},
        )
        await ws_manager.broadcast_json(
            make_event(
                "procurement.po_created",
                {"po_number": po.po_number, "supplier": supplier.name, "total": float(po.total_amount)},
            )
        )
        return po

    async def get(self, pk: uuid.UUID) -> PurchaseOrder:
        po = await self._pos.get_active(pk)
        if not po:
            raise NotFoundError("Purchase order not found.")
        return po

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        status: str | None = None,
        supplier_id: uuid.UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[PurchaseOrder], int]:
        offset = (page - 1) * size
        return await self._pos.get_all_paginated(
            offset=offset,
            limit=size,
            search=search,
            status=status,
            supplier_id=supplier_id,
            from_date=from_date,
            to_date=to_date,
        )

    async def update(
        self,
        pk: uuid.UUID,
        payload: PurchaseOrderUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> PurchaseOrder:
        po = await self.get(pk)
        if po.status not in _EDITABLE_STATUSES:
            raise ValidationError(f"Only DRAFT purchase orders can be edited. Current status: {po.status}")

        updates: dict[str, Any] = {}
        if payload.supplier_id is not None:
            supplier = await self._suppliers.get_active(payload.supplier_id)
            if not supplier:
                raise NotFoundError("Supplier not found.")
            updates["supplier_id"] = payload.supplier_id
        for field in ("order_date", "expected_delivery_date", "notes", "terms_conditions", "shipping_address"):
            val = getattr(payload, field, None)
            if val is not None:
                updates[field] = val

        if updates:
            await self._pos.update(po, **updates)

        if payload.items is not None:
            # Remove existing items and replace with new set
            for existing in list(po.items):
                await self._session.delete(existing)
            await self._session.flush()

            for item_payload in payload.items:
                product = await self._products.get_active(item_payload.product_id)
                if not product:
                    raise NotFoundError(f"Product {item_payload.product_id} not found.")
                line_total = _calc_line_total(
                    item_payload.quantity_ordered,
                    item_payload.unit_price,
                    item_payload.discount_percent,
                    item_payload.tax_percent,
                )
                item = PurchaseOrderItem(
                    purchase_order_id=po.id,
                    product_id=item_payload.product_id,
                    quantity_ordered=item_payload.quantity_ordered,
                    unit_price=item_payload.unit_price,
                    discount_percent=item_payload.discount_percent,
                    tax_percent=item_payload.tax_percent,
                    line_total=line_total,
                    quantity_received=0,
                    notes=item_payload.notes,
                )
                self._session.add(item)
            await self._session.flush()

        po = await self._pos.get_active(po.id)
        _recalc_po_totals(po)
        await self._session.flush()
        po = await self._pos.get_active(po.id)

        await self._audit.log(
            actor_id=actor.id,
            action="po:update",
            resource_type="purchase_orders",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return po

    async def delete(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> None:
        po = await self.get(pk)
        if po.status not in _EDITABLE_STATUSES:
            raise ValidationError("Only DRAFT purchase orders can be deleted.")
        await self._pos.update(
            po,
            is_deleted=True,
            deleted_at=datetime.now(UTC),
        )
        await self._audit.log(
            actor_id=actor.id,
            action="po:delete",
            resource_type="purchase_orders",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )

    async def submit(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> PurchaseOrder:
        po = await self.get(pk)
        if po.status not in _SUBMITTABLE_STATUSES:
            raise ValidationError(f"Cannot submit a PO in {po.status} status.")
        if not po.items:
            raise ValidationError("Cannot submit a purchase order with no items.")
        await self._pos.update(
            po,
            status=POStatus.SUBMITTED,
            submitted_by_id=actor.id,
            submitted_at=datetime.now(UTC),
        )
        po = await self._pos.get_active(po.id)
        await self._audit.log(
            actor_id=actor.id,
            action="po:submit",
            resource_type="purchase_orders",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        await ws_manager.broadcast_json(
            make_event(
                "procurement.po_submitted",
                {"po_number": po.po_number, "submitted_by": actor.full_name},
            )
        )
        return po

    async def approve(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> PurchaseOrder:
        po = await self.get(pk)
        if po.status not in _APPROVABLE_STATUSES:
            raise ValidationError(f"Cannot approve a PO in {po.status} status.")
        await self._pos.update(
            po,
            status=POStatus.APPROVED,
            approved_by_id=actor.id,
            approved_at=datetime.now(UTC),
        )
        po = await self._pos.get_active(po.id)
        await self._audit.log(
            actor_id=actor.id,
            action="po:approve",
            resource_type="purchase_orders",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        await ws_manager.broadcast_json(
            make_event(
                "procurement.po_approved",
                {"po_number": po.po_number, "approved_by": actor.full_name},
            )
        )
        return po

    async def reject(
        self,
        pk: uuid.UUID,
        reason: str,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> PurchaseOrder:
        po = await self.get(pk)
        if po.status not in _REJECTABLE_STATUSES:
            raise ValidationError(f"Cannot reject a PO in {po.status} status.")
        await self._pos.update(
            po,
            status=POStatus.REJECTED,
            rejected_by_id=actor.id,
            rejected_at=datetime.now(UTC),
            rejection_reason=reason,
        )
        po = await self._pos.get_active(po.id)
        await self._audit.log(
            actor_id=actor.id,
            action="po:reject",
            resource_type="purchase_orders",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
            detail={"reason": reason},
        )
        await ws_manager.broadcast_json(
            make_event(
                "procurement.po_rejected",
                {"po_number": po.po_number, "reason": reason},
            )
        )
        return po

    async def cancel(
        self,
        pk: uuid.UUID,
        reason: str,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> PurchaseOrder:
        po = await self.get(pk)
        if po.status not in _CANCELLABLE_PO_STATUSES:
            raise ValidationError(f"Cannot cancel a PO in {po.status} status.")
        await self._pos.update(
            po,
            status=POStatus.CANCELLED,
            cancelled_by_id=actor.id,
            cancelled_at=datetime.now(UTC),
            cancellation_reason=reason,
        )
        po = await self._pos.get_active(po.id)
        await self._audit.log(
            actor_id=actor.id,
            action="po:cancel",
            resource_type="purchase_orders",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
            detail={"reason": reason},
        )
        await ws_manager.broadcast_json(
            make_event(
                "procurement.po_cancelled",
                {"po_number": po.po_number, "reason": reason},
            )
        )
        return po

    async def duplicate(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> PurchaseOrder:
        original = await self.get(pk)
        items_payload = [
            POItemCreate(
                product_id=item.product_id,
                quantity_ordered=float(item.quantity_ordered),
                unit_price=float(item.unit_price),
                discount_percent=float(item.discount_percent),
                tax_percent=float(item.tax_percent),
                notes=item.notes,
            )
            for item in original.items
        ]
        dup_payload = PurchaseOrderCreate(
            supplier_id=original.supplier_id,
            order_date=datetime.now(UTC),
            expected_delivery_date=original.expected_delivery_date,
            notes=original.notes,
            terms_conditions=original.terms_conditions,
            shipping_address=original.shipping_address,
            items=items_payload,
        )
        return await self.create(dup_payload, actor=actor, ip_address=ip_address)

    async def send_email(
        self,
        pk: uuid.UUID,
        *,
        to_email: str | None = None,
        message: str | None = None,
        actor: User,
        ip_address: str | None = None,
    ) -> PurchaseOrder:
        po = await self.get(pk)
        if po.status not in (POStatus.APPROVED, POStatus.PARTIALLY_RECEIVED, POStatus.FULLY_RECEIVED):
            raise ValidationError("Only Approved or Received POs can be emailed.")

        recipient = to_email or (po.supplier.email if po.supplier else None)
        if not recipient:
            raise ValidationError("No email address available for supplier. Please provide to_email.")

        html = _build_po_email_html(po, message)
        svc = EmailService()
        await svc.send(
            to_email=recipient,
            subject=f"Purchase Order {po.po_number}",
            html_body=html,
        )
        await self._pos.update(
            po,
            email_sent_at=datetime.now(UTC),
            email_sent_to=recipient,
        )
        po = await self._pos.get_active(po.id)
        await self._audit.log(
            actor_id=actor.id,
            action="po:email",
            resource_type="purchase_orders",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
            detail={"to": recipient},
        )
        await ws_manager.broadcast_json(
            make_event(
                "procurement.po_emailed",
                {"po_number": po.po_number, "to": recipient},
            )
        )
        return po

    async def get_for_print(self, pk: uuid.UUID) -> dict:
        po = await self.get(pk)
        return _build_po_print_data(po)

    async def get_for_report(
        self,
        *,
        supplier_id: uuid.UUID | None = None,
        status: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[PurchaseOrder]:
        return await self._pos.get_for_report(
            supplier_id=supplier_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
        )


class GRNService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._grns = GRNRepository(session)
        self._pos = PurchaseOrderRepository(session)
        self._products = ProductRepository(session)
        self._ledger = InventoryLedgerRepository(session)
        self._audit = AuditLogRepository(session)

    async def create(
        self,
        payload: GRNCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> GRN:
        po = await self._pos.get_active(payload.purchase_order_id)
        if not po:
            raise NotFoundError("Purchase order not found.")
        if po.status not in _GRN_ALLOWED_PO_STATUSES:
            raise ValidationError(
                f"GRNs can only be created for Approved or Partially Received POs. "
                f"Current status: {po.status}"
            )

        # Validate items against PO
        po_items_by_id = {item.id: item for item in po.items}
        for grn_item in payload.items:
            po_item = po_items_by_id.get(grn_item.po_item_id)
            if not po_item:
                raise NotFoundError(f"PO item {grn_item.po_item_id} not found on this PO.")
            if po_item.product_id != grn_item.product_id:
                raise ValidationError(
                    f"Product mismatch for PO item {grn_item.po_item_id}."
                )
            # Check we are not receiving more than remaining
            remaining = float(po_item.quantity_ordered) - float(po_item.quantity_received)
            if float(grn_item.quantity_received) > remaining + 1e-6:
                raise ValidationError(
                    f"Cannot receive {grn_item.quantity_received} units for product "
                    f"{grn_item.product_id}. Remaining to receive: {remaining:.4f}"
                )

        grn_number = await self._grns.get_next_grn_number()
        grn = await self._grns.create(
            grn_number=grn_number,
            purchase_order_id=payload.purchase_order_id,
            status=GRNStatus.DRAFT,
            received_date=payload.received_date,
            delivery_note_number=payload.delivery_note_number,
            notes=payload.notes,
            created_by_id=actor.id,
        )

        for grn_item_payload in payload.items:
            item = GRNItem(
                grn_id=grn.id,
                po_item_id=grn_item_payload.po_item_id,
                product_id=grn_item_payload.product_id,
                quantity_received=grn_item_payload.quantity_received,
                unit_cost=grn_item_payload.unit_cost,
                notes=grn_item_payload.notes,
            )
            self._session.add(item)

        await self._session.flush()
        grn = await self._grns.get_active(grn.id)

        await self._audit.log(
            actor_id=actor.id,
            action="grn:create",
            resource_type="grns",
            resource_id=str(grn.id),
            ip_address=ip_address,
            status="success",
            detail={"grn_number": grn.grn_number},
        )
        await ws_manager.broadcast_json(
            make_event(
                "procurement.grn_created",
                {"grn_number": grn.grn_number, "po_number": po.po_number},
            )
        )
        return grn

    async def get(self, pk: uuid.UUID) -> GRN:
        grn = await self._grns.get_active(pk)
        if not grn:
            raise NotFoundError("GRN not found.")
        return grn

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        status: str | None = None,
        po_id: uuid.UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[GRN], int]:
        offset = (page - 1) * size
        return await self._grns.get_all_paginated(
            offset=offset,
            limit=size,
            search=search,
            status=status,
            po_id=po_id,
            from_date=from_date,
            to_date=to_date,
        )

    async def update(
        self,
        pk: uuid.UUID,
        payload: GRNUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> GRN:
        grn = await self.get(pk)
        if grn.status != GRNStatus.DRAFT:
            raise ValidationError("Only DRAFT GRNs can be edited.")

        updates: dict[str, Any] = {}
        for field in ("received_date", "delivery_note_number", "notes"):
            val = getattr(payload, field, None)
            if val is not None:
                updates[field] = val
        if updates:
            await self._grns.update(grn, **updates)

        if payload.items is not None:
            po = await self._pos.get_active(grn.purchase_order_id)
            if not po:
                raise NotFoundError("Associated purchase order not found.")
            po_items_by_id = {item.id: item for item in po.items}

            for existing in list(grn.items):
                await self._session.delete(existing)
            await self._session.flush()

            for grn_item_payload in payload.items:
                po_item = po_items_by_id.get(grn_item_payload.po_item_id)
                if not po_item:
                    raise NotFoundError(f"PO item {grn_item_payload.po_item_id} not found.")
                remaining = float(po_item.quantity_ordered) - float(po_item.quantity_received)
                if float(grn_item_payload.quantity_received) > remaining + 1e-6:
                    raise ValidationError(
                        f"Cannot receive more than remaining quantity {remaining:.4f}."
                    )
                item = GRNItem(
                    grn_id=grn.id,
                    po_item_id=grn_item_payload.po_item_id,
                    product_id=grn_item_payload.product_id,
                    quantity_received=grn_item_payload.quantity_received,
                    unit_cost=grn_item_payload.unit_cost,
                    notes=grn_item_payload.notes,
                )
                self._session.add(item)
            await self._session.flush()

        grn = await self._grns.get_active(grn.id)
        await self._audit.log(
            actor_id=actor.id,
            action="grn:update",
            resource_type="grns",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return grn

    async def submit(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> GRN:
        grn = await self.get(pk)
        if grn.status != GRNStatus.DRAFT:
            raise ValidationError(f"Cannot submit GRN in {grn.status} status.")
        if not grn.items:
            raise ValidationError("Cannot submit a GRN with no items.")
        await self._grns.update(
            grn,
            status=GRNStatus.SUBMITTED,
            submitted_by_id=actor.id,
            submitted_at=datetime.now(UTC),
        )
        grn = await self._grns.get_active(grn.id)
        await self._audit.log(
            actor_id=actor.id,
            action="grn:submit",
            resource_type="grns",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        return grn

    async def approve(
        self, pk: uuid.UUID, *, actor: User, ip_address: str | None = None
    ) -> GRN:
        grn = await self.get(pk)
        if grn.status != GRNStatus.SUBMITTED:
            raise ValidationError(f"Cannot approve GRN in {grn.status} status.")

        # Post inventory for each item
        for grn_item in grn.items:
            current_stock = await self._ledger.get_current_stock(grn_item.product_id)
            qty_change = float(grn_item.quantity_received)
            new_stock = current_stock + qty_change
            await self._ledger.append(
                product_id=grn_item.product_id,
                entry_type=LedgerEntryType.PURCHASE_RECEIPT,
                quantity_before=current_stock,
                quantity_change=qty_change,
                quantity_after=new_stock,
                unit_cost=float(grn_item.unit_cost),
                grn_id=grn.id,
                reference_number=grn.grn_number,
                notes=f"GRN approval: {grn.grn_number}",
                created_by_id=actor.id,
            )
            # Update po item received qty
            po_item = grn_item.po_item
            new_received = float(po_item.quantity_received) + qty_change
            await self._session.execute(
                _sa_update(PurchaseOrderItem)
                .where(PurchaseOrderItem.id == po_item.id)
                .values(quantity_received=new_received)
            )

        # Refresh PO items and update PO status
        po = await self._pos.get_active(grn.purchase_order_id)
        all_received = True
        any_received = False
        for po_item in po.items:
            ordered = float(po_item.quantity_ordered)
            received = float(po_item.quantity_received)
            if received >= ordered - 1e-6:
                any_received = True
            else:
                all_received = False
                if received > 1e-6:
                    any_received = True

        if all_received:
            new_po_status = POStatus.FULLY_RECEIVED
        elif any_received:
            new_po_status = POStatus.PARTIALLY_RECEIVED
        else:
            new_po_status = po.status

        await self._pos.update(po, status=new_po_status)
        await self._grns.update(
            grn,
            status=GRNStatus.APPROVED,
            approved_by_id=actor.id,
            approved_at=datetime.now(UTC),
        )
        grn = await self._grns.get_active(grn.id)
        await self._audit.log(
            actor_id=actor.id,
            action="grn:approve",
            resource_type="grns",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
        )
        await ws_manager.broadcast_json(
            make_event(
                "procurement.grn_approved",
                {"grn_number": grn.grn_number},
            )
        )
        return grn

    async def cancel(
        self,
        pk: uuid.UUID,
        reason: str,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> GRN:
        grn = await self.get(pk)
        if grn.status == GRNStatus.APPROVED:
            raise ValidationError("Cannot cancel an Approved GRN.")
        await self._grns.update(
            grn,
            status=GRNStatus.CANCELLED,
            cancelled_by_id=actor.id,
            cancelled_at=datetime.now(UTC),
            cancellation_reason=reason,
        )
        grn = await self._grns.get_active(grn.id)
        await self._audit.log(
            actor_id=actor.id,
            action="grn:cancel",
            resource_type="grns",
            resource_id=str(pk),
            ip_address=ip_address,
            status="success",
            detail={"reason": reason},
        )
        await ws_manager.broadcast_json(
            make_event(
                "procurement.grn_cancelled",
                {"grn_number": grn.grn_number, "reason": reason},
            )
        )
        return grn

    async def get_for_report(
        self,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        status: str | None = None,
    ) -> list[GRN]:
        return await self._grns.get_for_report(
            from_date=from_date,
            to_date=to_date,
            status=status,
        )


class InventoryLedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self._ledger = InventoryLedgerRepository(session)

    async def get_for_product(
        self,
        product_id: uuid.UUID,
        *,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[InventoryLedger], int]:
        offset = (page - 1) * size
        return await self._ledger.get_for_product(product_id, offset=offset, limit=size)

    async def get_current_stock(self, product_id: uuid.UUID) -> float:
        return await self._ledger.get_current_stock(product_id)


class ProcurementDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._pos = PurchaseOrderRepository(session)
        self._grns = GRNRepository(session)

    async def get_summary(self) -> dict:
        from datetime import date, timedelta
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        pending_pos = await self._pos.count_by_status(POStatus.SUBMITTED)
        pending_grns = await self._grns.count_by_status(GRNStatus.SUBMITTED)
        total_po_month = await self._pos.sum_total_by_date_range(month_start, now)
        total_po_all = await self._pos.sum_total_all()
        approved_pos_month = await self._pos.count_approved_since(month_start)
        approved_grns_month = await self._grns.count_approved_since(month_start)
        recent_pos = await self._pos.get_recent_activities(limit=10)

        activities = []
        for po in recent_pos:
            activities.append({
                "type": "purchase_order",
                "id": str(po.id),
                "reference": po.po_number,
                "status": po.status,
                "supplier": po.supplier.name if po.supplier else None,
                "amount": float(po.total_amount),
                "updated_at": po.updated_at.isoformat(),
            })

        return {
            "pending_purchase_orders": pending_pos,
            "pending_grns": pending_grns,
            "total_po_this_month": total_po_month,
            "total_po_all_time": total_po_all,
            "approved_pos_this_month": approved_pos_month,
            "approved_grns_this_month": approved_grns_month,
            "recent_activities": activities,
        }


# ---------------------------------------------------------------------------
# Email template helpers
# ---------------------------------------------------------------------------

_PO_EMAIL_STYLE = """
  font-family: Arial, sans-serif;
  max-width: 750px;
  margin: 0 auto;
  padding: 24px;
  color: #333;
"""


def _build_po_email_html(po: PurchaseOrder, custom_message: str | None = None) -> str:
    items_rows = ""
    for item in po.items:
        product_name = item.product.name if item.product else str(item.product_id)
        items_rows += f"""
        <tr style="background:#f9f9f9">
          <td style="padding:8px;border:1px solid #ddd">{product_name}</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center">{float(item.quantity_ordered):.2f}</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:right">{float(item.unit_price):.2f}</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:right">{float(item.discount_percent):.2f}%</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:right">{float(item.tax_percent):.2f}%</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:right;font-weight:bold">{float(item.line_total):.2f}</td>
        </tr>"""

    message_block = f'<p style="margin:16px 0;background:#fff3cd;padding:12px;border-radius:4px">{custom_message}</p>' if custom_message else ""
    supplier_name = po.supplier.name if po.supplier else "N/A"
    supplier_email = po.supplier.email if po.supplier else "N/A"
    contact = po.supplier.contact_person if po.supplier else "N/A"

    return f"""
<div style="{_PO_EMAIL_STYLE}">
  <h2 style="color:#2B5797;border-bottom:2px solid #2B5797;padding-bottom:8px">Purchase Order — {po.po_number}</h2>
  {message_block}
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px">
    <tr>
      <td width="50%">
        <strong>Supplier</strong><br>
        {supplier_name}<br>
        {supplier_email}<br>
        {contact}
      </td>
      <td width="50%" style="text-align:right">
        <strong>PO Number:</strong> {po.po_number}<br>
        <strong>Order Date:</strong> {po.order_date.strftime('%Y-%m-%d')}<br>
        <strong>Status:</strong> {po.status}
      </td>
    </tr>
  </table>
  <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:24px">
    <thead>
      <tr style="background:#2B5797;color:#fff">
        <th style="padding:10px;border:1px solid #ddd;text-align:left">Product</th>
        <th style="padding:10px;border:1px solid #ddd;text-align:center">Qty</th>
        <th style="padding:10px;border:1px solid #ddd;text-align:right">Unit Price</th>
        <th style="padding:10px;border:1px solid #ddd;text-align:right">Discount</th>
        <th style="padding:10px;border:1px solid #ddd;text-align:right">Tax</th>
        <th style="padding:10px;border:1px solid #ddd;text-align:right">Line Total</th>
      </tr>
    </thead>
    <tbody>{items_rows}</tbody>
  </table>
  <table width="300" cellpadding="0" cellspacing="0" style="margin-left:auto;border-collapse:collapse">
    <tr><td style="padding:6px 12px">Subtotal</td><td style="padding:6px 12px;text-align:right">{float(po.subtotal):.2f}</td></tr>
    <tr><td style="padding:6px 12px">Discount</td><td style="padding:6px 12px;text-align:right">-{float(po.discount_amount):.2f}</td></tr>
    <tr><td style="padding:6px 12px">Tax</td><td style="padding:6px 12px;text-align:right">{float(po.tax_amount):.2f}</td></tr>
    <tr style="background:#2B5797;color:#fff;font-weight:bold">
      <td style="padding:8px 12px">TOTAL</td>
      <td style="padding:8px 12px;text-align:right">{float(po.total_amount):.2f}</td>
    </tr>
  </table>
  {('<p style="margin-top:24px"><strong>Notes:</strong> ' + po.notes + '</p>') if po.notes else ''}
  {('<p><strong>Terms & Conditions:</strong> ' + po.terms_conditions + '</p>') if po.terms_conditions else ''}
  <hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
  <p style="font-size:12px;color:#777">This is an automated Purchase Order from SIMS Lite. Please do not reply to this email directly.</p>
</div>
"""


def _build_po_print_data(po: PurchaseOrder) -> dict:
    return {
        "po_number": po.po_number,
        "status": po.status,
        "order_date": po.order_date.isoformat(),
        "expected_delivery_date": po.expected_delivery_date.isoformat() if po.expected_delivery_date else None,
        "supplier": {
            "id": str(po.supplier.id) if po.supplier else None,
            "name": po.supplier.name if po.supplier else None,
            "email": po.supplier.email if po.supplier else None,
            "contact_person": po.supplier.contact_person if po.supplier else None,
            "address": po.supplier.address if po.supplier else None,
        },
        "items": [
            {
                "product_name": item.product.name if item.product else str(item.product_id),
                "sku": item.product.sku if item.product else None,
                "quantity_ordered": float(item.quantity_ordered),
                "unit_price": float(item.unit_price),
                "discount_percent": float(item.discount_percent),
                "tax_percent": float(item.tax_percent),
                "line_total": float(item.line_total),
            }
            for item in po.items
        ],
        "subtotal": float(po.subtotal),
        "discount_amount": float(po.discount_amount),
        "tax_amount": float(po.tax_amount),
        "total_amount": float(po.total_amount),
        "notes": po.notes,
        "terms_conditions": po.terms_conditions,
        "shipping_address": po.shipping_address,
    }
