"""
Inventory service layer — Phase 4.

Business logic for:
- InventoryService         — current stock, summary, valuation, low/out-of-stock
- InventoryLedgerService   — ledger queries
- StockAdjustmentService   — CRUD + workflow (submit/approve/cancel)
- InventoryDashboardService — dashboard KPIs
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.inventory import (
    Inventory,
    InventoryLedgerEntry,
    LedgerEntryType,
    LedgerReferenceType,
    StockAdjustment,
    StockAdjustmentItem,
    StockAdjustmentStatus,
    StockAdjustmentType,
)
from app.models.user import User
from app.repositories.audit_log import AuditLogRepository
from app.repositories.inventory import (
    InventoryLedgerEntryRepository,
    InventoryRepository,
    StockAdjustmentRepository,
)
from app.repositories.master_data import ProductRepository
from app.schemas.inventory import (
    StockAdjustmentCreate,
    StockAdjustmentUpdate,
)
from app.websockets.events import EventType, make_event
from app.websockets.manager import ws_manager

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Status-transition guards
# ---------------------------------------------------------------------------

_ADJ_EDITABLE = {StockAdjustmentStatus.DRAFT}
_ADJ_SUBMITTABLE = {StockAdjustmentStatus.DRAFT}
_ADJ_APPROVABLE = {StockAdjustmentStatus.SUBMITTED}
_ADJ_CANCELLABLE = {StockAdjustmentStatus.DRAFT, StockAdjustmentStatus.SUBMITTED}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


async def _apply_inventory_change(
    inv: Inventory,
    qty_change: float,
    unit_cost: float,
    *,
    inventory_repo: InventoryRepository,
    ledger_repo: InventoryLedgerEntryRepository,
    entry_type: str,
    reference_type: str | None,
    reference_id: uuid.UUID | None,
    reference_number: str | None,
    notes: str | None,
    created_by_id: uuid.UUID | None,
) -> InventoryLedgerEntry:
    """
    Atomically update the inventory row and append a ledger entry.

    qty_change can be positive (increase) or negative (decrease).
    Raises ValidationError if the result would go below zero.
    """
    qty_before = float(inv.quantity_on_hand)
    qty_after = round(qty_before + qty_change, 4)

    if qty_after < 0:
        raise ValidationError(
            f"Insufficient stock. Current: {qty_before}, Change: {qty_change}. "
            f"Stock cannot go below zero."
        )

    # Update weighted average cost (only on increases)
    if qty_change > 0 and unit_cost > 0:
        total_value = qty_before * float(inv.average_cost) + qty_change * unit_cost
        new_qty = qty_after
        inv.average_cost = round(total_value / new_qty, 4) if new_qty > 0 else unit_cost

    inv.quantity_on_hand = qty_after
    inv.last_updated_at = _now()
    inv.last_transaction_type = entry_type
    inventory_repo.session.add(inv)
    await inventory_repo.session.flush()

    # Append immutable ledger record
    ledger_entry = await ledger_repo.append(
        product_id=inv.product_id,
        entry_type=entry_type,
        quantity_before=qty_before,
        quantity_change=qty_change,
        quantity_after=qty_after,
        unit_cost=unit_cost,
        reference_type=reference_type,
        reference_id=reference_id,
        reference_number=reference_number,
        notes=notes,
        created_by_id=created_by_id,
    )
    return ledger_entry


# ---------------------------------------------------------------------------
# InventoryService
# ---------------------------------------------------------------------------


class InventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._inv = InventoryRepository(session)
        self._ledger = InventoryLedgerEntryRepository(session)
        self._products = ProductRepository(session)

    async def get_by_product(self, product_id: uuid.UUID) -> Inventory:
        product = await self._products.get_active(product_id)
        if not product:
            raise NotFoundError("Product not found.")
        inv = await self._inv.get_by_product(product_id)
        if inv is None:
            # Return a virtual row with zero stock (don't persist until there's a movement)
            inv = Inventory(
                product_id=product_id,
                quantity_on_hand=0,
                average_cost=float(product.cost_price) if product.cost_price else 0,
            )
            inv.product = product
        return inv

    async def get_all(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        category_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        low_stock_only: bool = False,
        out_of_stock_only: bool = False,
    ) -> tuple[list[Inventory], int]:
        offset = (page - 1) * size
        return await self._inv.get_all_paginated(
            offset=offset,
            limit=size,
            search=search,
            category_id=category_id,
            supplier_id=supplier_id,
            low_stock_only=low_stock_only,
            out_of_stock_only=out_of_stock_only,
        )

    async def get_summary(self) -> dict:
        return await self._inv.get_summary()

    async def get_valuation(self) -> list[Inventory]:
        """Return all inventory rows for valuation report."""
        return await self._inv.get_all_for_report()

    async def get_low_stock(self, *, page: int = 1, size: int = 20) -> tuple[list[Inventory], int]:
        offset = (page - 1) * size
        return await self._inv.get_all_paginated(
            offset=offset,
            limit=size,
            low_stock_only=True,
        )

    async def get_out_of_stock(
        self, *, page: int = 1, size: int = 20
    ) -> tuple[list[Inventory], int]:
        offset = (page - 1) * size
        return await self._inv.get_all_paginated(
            offset=offset,
            limit=size,
            out_of_stock_only=True,
        )

    async def apply_grn_receipt(
        self,
        *,
        product_id: uuid.UUID,
        quantity: float,
        unit_cost: float,
        grn_id: uuid.UUID,
        grn_number: str,
        actor: User,
    ) -> InventoryLedgerEntry:
        """
        Increase inventory from an approved GRN.
        Called by the GRN approval workflow in procurement service.
        """
        inv = await self._inv.get_or_create(product_id)
        entry = await _apply_inventory_change(
            inv,
            qty_change=quantity,
            unit_cost=unit_cost,
            inventory_repo=self._inv,
            ledger_repo=self._ledger,
            entry_type=LedgerEntryType.PURCHASE_RECEIPT,
            reference_type=LedgerReferenceType.GRN,
            reference_id=grn_id,
            reference_number=grn_number,
            notes=f"GRN receipt: {grn_number}",
            created_by_id=actor.id,
        )

        # Publish WebSocket event
        qty_after = float(inv.quantity_on_hand)
        product = inv.product
        await ws_manager.broadcast_json(
            make_event(
                EventType.INVENTORY_INCREASED,
                {
                    "product_id": str(product_id),
                    "product_name": product.name if product else "",
                    "sku": product.sku if product else "",
                    "quantity_change": quantity,
                    "quantity_after": qty_after,
                    "reference_type": "GRN",
                    "reference_number": grn_number,
                },
            )
        )

        # Check for low stock / out-of-stock notifications
        await self._publish_stock_alerts(inv)

        return entry

    async def _publish_stock_alerts(self, inv: Inventory) -> None:
        """Publish low-stock / out-of-stock WebSocket events and notifications if thresholds crossed."""
        product = inv.product
        if not product:
            return
        qty = float(inv.quantity_on_hand)
        reorder = int(product.reorder_level or 0)

        if qty <= 0:
            await ws_manager.broadcast_json(
                make_event(
                    EventType.INVENTORY_OUT_OF_STOCK,
                    {
                        "product_id": str(inv.product_id),
                        "product_name": product.name,
                        "sku": product.sku,
                        "quantity_on_hand": qty,
                    },
                )
            )
            # Persistent notification
            try:
                from app.services.notification import NotificationEventService

                notifier = NotificationEventService(self._session)
                await notifier.notify_out_of_stock(product.name, inv.product_id)
            except Exception:  # noqa: BLE001
                logger.warning("Out-of-stock notification failed", product_id=str(inv.product_id))
        elif reorder > 0 and qty <= reorder:
            await ws_manager.broadcast_json(
                make_event(
                    EventType.INVENTORY_LOW_STOCK,
                    {
                        "product_id": str(inv.product_id),
                        "product_name": product.name,
                        "sku": product.sku,
                        "quantity_on_hand": qty,
                        "reorder_level": reorder,
                    },
                )
            )
            # Persistent notification
            try:
                from app.services.notification import NotificationEventService

                notifier = NotificationEventService(self._session)
                await notifier.notify_low_stock(product.name, inv.product_id, qty, float(reorder))
            except Exception:  # noqa: BLE001
                logger.warning("Low-stock notification failed", product_id=str(inv.product_id))


# ---------------------------------------------------------------------------
# InventoryLedgerService
# ---------------------------------------------------------------------------


class InventoryLedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._ledger = InventoryLedgerEntryRepository(session)

    async def get_all(
        self,
        *,
        page: int = 1,
        size: int = 50,
        product_id: uuid.UUID | None = None,
        entry_type: str | None = None,
        reference_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[InventoryLedgerEntry], int]:
        offset = (page - 1) * size
        return await self._ledger.get_all_paginated(
            offset=offset,
            limit=size,
            product_id=product_id,
            entry_type=entry_type,
            reference_type=reference_type,
            from_date=from_date,
            to_date=to_date,
        )

    async def get_by_id(self, entry_id: uuid.UUID) -> InventoryLedgerEntry:
        entry = await self._ledger.get_by_id(entry_id)
        if not entry:
            raise NotFoundError("Inventory ledger entry not found.")
        return entry

    async def get_for_product(
        self,
        product_id: uuid.UUID,
        *,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[InventoryLedgerEntry], int]:
        offset = (page - 1) * size
        return await self._ledger.get_for_product_paginated(
            product_id, offset=offset, limit=size
        )

    async def get_by_reference(
        self,
        reference_type: str,
        reference_id: uuid.UUID,
    ) -> list[InventoryLedgerEntry]:
        return await self._ledger.get_by_reference(reference_type, reference_id)

    async def get_all_for_report(
        self,
        *,
        product_id: uuid.UUID | None = None,
        entry_type: str | None = None,
        reference_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[InventoryLedgerEntry]:
        return await self._ledger.get_all_for_report(
            product_id=product_id,
            entry_type=entry_type,
            reference_type=reference_type,
            from_date=from_date,
            to_date=to_date,
        )


# ---------------------------------------------------------------------------
# StockAdjustmentService
# ---------------------------------------------------------------------------


class StockAdjustmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._adj = StockAdjustmentRepository(session)
        self._inv = InventoryRepository(session)
        self._ledger = InventoryLedgerEntryRepository(session)
        self._products = ProductRepository(session)
        self._audit = AuditLogRepository(session)

    async def create(
        self,
        payload: StockAdjustmentCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockAdjustment:
        # Validate all products exist
        for item_payload in payload.items:
            product = await self._products.get_active(item_payload.product_id)
            if not product:
                raise NotFoundError(
                    f"Product {item_payload.product_id} not found."
                )

        adj_number = await self._adj.get_next_adjustment_number()

        adj = StockAdjustment(
            adjustment_number=adj_number,
            adjustment_type=payload.adjustment_type,
            status=StockAdjustmentStatus.DRAFT,
            reason=payload.reason,
            notes=payload.notes,
            created_by_id=actor.id,
        )
        self._session.add(adj)
        await self._session.flush()

        for item_payload in payload.items:
            item = StockAdjustmentItem(
                stock_adjustment_id=adj.id,
                product_id=item_payload.product_id,
                quantity_adjusted=item_payload.quantity_adjusted,
                unit_cost=item_payload.unit_cost,
                notes=item_payload.notes,
            )
            self._session.add(item)

        await self._session.flush()
        await self._session.refresh(adj)

        await self._audit.log(
            actor_id=actor.id,
            action="stock_adjustment:create",
            resource_type="stock_adjustments",
            resource_id=str(adj.id),
            ip_address=ip_address,
            status="success",
            new_values={"adjustment_number": adj_number, "type": str(payload.adjustment_type)},
        )

        # Publish WebSocket event
        await ws_manager.broadcast_json(
            make_event(
                EventType.STOCK_ADJUSTMENT_CREATED,
                {
                    "id": str(adj.id),
                    "adjustment_number": adj_number,
                    "adjustment_type": str(payload.adjustment_type),
                    "created_by": actor.full_name,
                },
            )
        )

        return await self._adj.get_active(adj.id)  # type: ignore[return-value]

    async def get(self, adj_id: uuid.UUID) -> StockAdjustment:
        adj = await self._adj.get_active(adj_id)
        if not adj:
            raise NotFoundError("Stock adjustment not found.")
        return adj

    async def get_all(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        status: str | None = None,
        adjustment_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[StockAdjustment], int]:
        offset = (page - 1) * size
        return await self._adj.get_all_paginated(
            offset=offset,
            limit=size,
            search=search,
            status=status,
            adjustment_type=adjustment_type,
            from_date=from_date,
            to_date=to_date,
        )

    async def update(
        self,
        adj_id: uuid.UUID,
        payload: StockAdjustmentUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockAdjustment:
        adj = await self.get(adj_id)
        if adj.status not in _ADJ_EDITABLE:
            raise ValidationError(
                f"Cannot edit a stock adjustment in '{adj.status}' status. "
                "Only DRAFT adjustments can be edited."
            )

        if payload.adjustment_type is not None:
            adj.adjustment_type = payload.adjustment_type
        if payload.reason is not None:
            adj.reason = payload.reason
        if payload.notes is not None:
            adj.notes = payload.notes

        if payload.items is not None:
            # Validate all products
            for item_payload in payload.items:
                product = await self._products.get_active(item_payload.product_id)
                if not product:
                    raise NotFoundError(
                        f"Product {item_payload.product_id} not found."
                    )
            # Replace items
            for old_item in list(adj.items):
                await self._session.delete(old_item)
            await self._session.flush()

            for item_payload in payload.items:
                item = StockAdjustmentItem(
                    stock_adjustment_id=adj.id,
                    product_id=item_payload.product_id,
                    quantity_adjusted=item_payload.quantity_adjusted,
                    unit_cost=item_payload.unit_cost,
                    notes=item_payload.notes,
                )
                self._session.add(item)

        self._session.add(adj)
        await self._session.flush()
        await self._session.refresh(adj)

        await self._audit.log(
            actor_id=actor.id,
            action="stock_adjustment:update",
            resource_type="stock_adjustments",
            resource_id=str(adj_id),
            ip_address=ip_address,
            status="success",
        )
        return await self._adj.get_active(adj_id)  # type: ignore[return-value]

    async def delete(
        self,
        adj_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        adj = await self.get(adj_id)
        if adj.status not in _ADJ_EDITABLE:
            raise ValidationError(
                f"Cannot delete a stock adjustment in '{adj.status}' status. "
                "Only DRAFT adjustments can be deleted."
            )
        adj.is_deleted = True
        adj.deleted_at = _now()
        self._session.add(adj)
        await self._session.flush()

        await self._audit.log(
            actor_id=actor.id,
            action="stock_adjustment:delete",
            resource_type="stock_adjustments",
            resource_id=str(adj_id),
            ip_address=ip_address,
            status="success",
        )

    async def submit(
        self,
        adj_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockAdjustment:
        adj = await self.get(adj_id)
        if adj.status not in _ADJ_SUBMITTABLE:
            raise ValidationError(
                f"Cannot submit a stock adjustment in '{adj.status}' status."
            )
        if not adj.items:
            raise ValidationError("Cannot submit an adjustment with no items.")

        adj.status = StockAdjustmentStatus.SUBMITTED
        adj.submitted_by_id = actor.id
        adj.submitted_at = _now()
        self._session.add(adj)
        await self._session.flush()

        await self._audit.log(
            actor_id=actor.id,
            action="stock_adjustment:submit",
            resource_type="stock_adjustments",
            resource_id=str(adj_id),
            ip_address=ip_address,
            status="success",
        )

        await ws_manager.broadcast_json(
            make_event(
                EventType.STOCK_ADJUSTMENT_SUBMITTED,
                {
                    "id": str(adj_id),
                    "adjustment_number": adj.adjustment_number,
                    "submitted_by": actor.full_name,
                },
            )
        )
        return await self._adj.get_active(adj_id)  # type: ignore[return-value]

    async def approve(
        self,
        adj_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockAdjustment:
        adj = await self.get(adj_id)
        if adj.status not in _ADJ_APPROVABLE:
            raise ValidationError(
                f"Cannot approve a stock adjustment in '{adj.status}' status."
            )

        # Apply each item to inventory
        for item in adj.items:
            inv = await self._inv.get_or_create(item.product_id)

            # Determine direction
            if adj.adjustment_type == StockAdjustmentType.INCREASE:
                qty_change = float(item.quantity_adjusted)
                entry_type = LedgerEntryType.ADJUSTMENT_IN
            elif adj.adjustment_type == StockAdjustmentType.DECREASE:
                qty_change = -float(item.quantity_adjusted)
                entry_type = LedgerEntryType.ADJUSTMENT_OUT
            else:
                # RECOUNT: compare with current stock
                current = float(inv.quantity_on_hand)
                qty_change = float(item.quantity_adjusted) - current
                entry_type = (
                    LedgerEntryType.ADJUSTMENT_IN
                    if qty_change >= 0
                    else LedgerEntryType.ADJUSTMENT_OUT
                )

            entry = await _apply_inventory_change(
                inv,
                qty_change=qty_change,
                unit_cost=float(item.unit_cost),
                inventory_repo=self._inv,
                ledger_repo=self._ledger,
                entry_type=entry_type,
                reference_type=LedgerReferenceType.STOCK_ADJUSTMENT,
                reference_id=adj.id,
                reference_number=adj.adjustment_number,
                notes=item.notes or f"Adjustment: {adj.reason}",
                created_by_id=actor.id,
            )

            # Publish per-product inventory event
            product = inv.product
            event_type = (
                EventType.INVENTORY_INCREASED
                if qty_change > 0
                else EventType.INVENTORY_DECREASED
            )
            await ws_manager.broadcast_json(
                make_event(
                    event_type,
                    {
                        "product_id": str(item.product_id),
                        "product_name": product.name if product else "",
                        "sku": product.sku if product else "",
                        "quantity_change": qty_change,
                        "quantity_after": float(inv.quantity_on_hand),
                        "reference_type": "STOCK_ADJUSTMENT",
                        "reference_number": adj.adjustment_number,
                    },
                )
            )

            # Alert checks
            svc = InventoryService(self._session)
            await svc._publish_stock_alerts(inv)

        # Mark adjustment approved
        adj.status = StockAdjustmentStatus.APPROVED
        adj.approved_by_id = actor.id
        adj.approved_at = _now()
        self._session.add(adj)
        await self._session.flush()

        await self._audit.log(
            actor_id=actor.id,
            action="stock_adjustment:approve",
            resource_type="stock_adjustments",
            resource_id=str(adj_id),
            ip_address=ip_address,
            status="success",
        )

        await ws_manager.broadcast_json(
            make_event(
                EventType.STOCK_ADJUSTMENT_APPROVED,
                {
                    "id": str(adj_id),
                    "adjustment_number": adj.adjustment_number,
                    "approved_by": actor.full_name,
                },
            )
        )
        return await self._adj.get_active(adj_id)  # type: ignore[return-value]

    async def cancel(
        self,
        adj_id: uuid.UUID,
        reason: str,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockAdjustment:
        adj = await self.get(adj_id)
        if adj.status not in _ADJ_CANCELLABLE:
            raise ValidationError(
                f"Cannot cancel a stock adjustment in '{adj.status}' status."
            )

        adj.status = StockAdjustmentStatus.CANCELLED
        adj.cancelled_by_id = actor.id
        adj.cancelled_at = _now()
        adj.cancellation_reason = reason
        self._session.add(adj)
        await self._session.flush()

        await self._audit.log(
            actor_id=actor.id,
            action="stock_adjustment:cancel",
            resource_type="stock_adjustments",
            resource_id=str(adj_id),
            ip_address=ip_address,
            status="success",
            new_values={"reason": reason},
        )

        await ws_manager.broadcast_json(
            make_event(
                EventType.STOCK_ADJUSTMENT_CANCELLED,
                {
                    "id": str(adj_id),
                    "adjustment_number": adj.adjustment_number,
                    "cancelled_by": actor.full_name,
                    "reason": reason,
                },
            )
        )
        return await self._adj.get_active(adj_id)  # type: ignore[return-value]

    async def get_for_report(
        self,
        *,
        status: str | None = None,
        adjustment_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[StockAdjustment]:
        return await self._adj.get_for_report(
            status=status,
            adjustment_type=adjustment_type,
            from_date=from_date,
            to_date=to_date,
        )


# ---------------------------------------------------------------------------
# InventoryDashboardService
# ---------------------------------------------------------------------------


class InventoryDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._inv = InventoryRepository(session)
        self._adj = StockAdjustmentRepository(session)
        self._ledger = InventoryLedgerEntryRepository(session)

    async def get_summary(self) -> dict:
        inv_summary = await self._inv.get_summary()
        pending_adj = await self._adj.count_by_status(StockAdjustmentStatus.SUBMITTED)

        # Recent movements (last 10 ledger entries)
        recent_entries, _ = await self._ledger.get_all_paginated(offset=0, limit=10)
        recent_movements = []
        for entry in recent_entries:
            recent_movements.append(
                {
                    "id": str(entry.id),
                    "product_id": str(entry.product_id),
                    "product_name": entry.product.name if entry.product else "",
                    "sku": entry.product.sku if entry.product else "",
                    "entry_type": entry.entry_type,
                    "quantity_change": float(entry.quantity_change),
                    "quantity_after": float(entry.quantity_after),
                    "reference_type": entry.reference_type,
                    "reference_number": entry.reference_number,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                }
            )

        return {
            **inv_summary,
            "pending_adjustments": pending_adj,
            "recent_movements": recent_movements,
        }
