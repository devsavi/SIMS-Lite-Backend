"""
Stock Release service layer — Phase 5.

Business logic for:
- StockReleaseService          — CRUD + workflow (submit / approve / cancel)
- StockReleaseDashboardService — dashboard KPIs (today's releases, monthly qty, top products)

Key invariants:
- Inventory is NEVER deducted before approval.
- Inventory can NEVER go below zero.
- Every approval creates immutable InventoryLedgerEntry records.
- Approved documents are read-only (no edits / deletes after approval).
- Cancelled documents have no inventory impact.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.inventory import (
    InventoryLedgerEntry,
    LedgerEntryType,
    LedgerReferenceType,
)
from app.models.stock_release import (
    StockRelease,
    StockReleaseItem,
    StockReleasePurpose,
    StockReleaseStatus,
)
from app.models.user import User
from app.repositories.audit_log import AuditLogRepository
from app.repositories.inventory import (
    InventoryLedgerEntryRepository,
    InventoryRepository,
)
from app.repositories.master_data import ProductRepository
from app.repositories.stock_release import StockReleaseRepository
from app.schemas.stock_release import StockReleaseCreate, StockReleaseUpdate
from app.services.inventory import InventoryService, _apply_inventory_change
from app.websockets.events import EventType, make_event
from app.websockets.manager import ws_manager

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Status-transition guards
# ---------------------------------------------------------------------------

_SR_EDITABLE = {StockReleaseStatus.DRAFT}
_SR_SUBMITTABLE = {StockReleaseStatus.DRAFT}
_SR_APPROVABLE = {StockReleaseStatus.SUBMITTED}
_SR_CANCELLABLE = {StockReleaseStatus.DRAFT, StockReleaseStatus.SUBMITTED}


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# StockReleaseService
# ---------------------------------------------------------------------------


class StockReleaseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sr = StockReleaseRepository(session)
        self._inv = InventoryRepository(session)
        self._ledger = InventoryLedgerEntryRepository(session)
        self._products = ProductRepository(session)
        self._audit = AuditLogRepository(session)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        payload: StockReleaseCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockRelease:
        """Create a new DRAFT stock release."""
        # Validate all products exist and are active
        for item_payload in payload.items:
            product = await self._products.get_active(item_payload.product_id)
            if not product:
                raise NotFoundError(
                    f"Product {item_payload.product_id} not found."
                )

        release_number = await self._sr.get_next_release_number()

        sr = StockRelease(
            release_number=release_number,
            purpose=payload.purpose,
            status=StockReleaseStatus.DRAFT,
            release_date=payload.release_date,
            notes=payload.notes,
            reference_document=payload.reference_document,
            total_quantity=0,
            total_cost=0,
            created_by_id=actor.id,
        )
        self._session.add(sr)
        await self._session.flush()

        for item_payload in payload.items:
            item = StockReleaseItem(
                stock_release_id=sr.id,
                product_id=item_payload.product_id,
                quantity_requested=item_payload.quantity_requested,
                unit_cost=0,       # captured from inventory average cost at approval
                line_total=0,
                notes=item_payload.notes,
            )
            self._session.add(item)

        await self._session.flush()
        await self._session.refresh(sr)

        await self._audit.log(
            actor_id=actor.id,
            action="stock_release:create",
            resource_type="stock_releases",
            resource_id=str(sr.id),
            ip_address=ip_address,
            status="success",
            new_values={"release_number": release_number, "purpose": str(payload.purpose)},
        )

        await ws_manager.broadcast_json(
            make_event(
                EventType.STOCK_RELEASE_CREATED,
                {
                    "id": str(sr.id),
                    "release_number": release_number,
                    "purpose": str(payload.purpose),
                    "created_by": actor.full_name,
                },
            )
        )

        # Auto-notification: notify admins of new stock release
        try:
            from app.services.notification import NotificationEventService

            notifier = NotificationEventService(self._session)
            await notifier.notify_stock_release_created(release_number, sr.id, actor)
        except Exception:  # noqa: BLE001
            logger.warning("Stock release create notification failed", sr_id=str(sr.id))

        return await self._sr.get_active(sr.id)  # type: ignore[return-value]

    async def get(self, sr_id: uuid.UUID) -> StockRelease:
        sr = await self._sr.get_active(sr_id)
        if not sr:
            raise NotFoundError("Stock release not found.")
        return sr

    async def get_all(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
        status: str | None = None,
        purpose: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[StockRelease], int]:
        offset = (page - 1) * size
        return await self._sr.get_all_paginated(
            offset=offset,
            limit=size,
            search=search,
            status=status,
            purpose=purpose,
            from_date=from_date,
            to_date=to_date,
        )

    async def update(
        self,
        sr_id: uuid.UUID,
        payload: StockReleaseUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockRelease:
        """Update a DRAFT stock release."""
        sr = await self.get(sr_id)
        if sr.status not in _SR_EDITABLE:
            raise ValidationError(
                f"Cannot edit a stock release in '{sr.status}' status. "
                "Only DRAFT releases can be edited."
            )

        if payload.purpose is not None:
            sr.purpose = payload.purpose
        if payload.release_date is not None:
            sr.release_date = payload.release_date
        if payload.notes is not None:
            sr.notes = payload.notes
        if payload.reference_document is not None:
            sr.reference_document = payload.reference_document

        if payload.items is not None:
            # Validate all products exist
            for item_payload in payload.items:
                product = await self._products.get_active(item_payload.product_id)
                if not product:
                    raise NotFoundError(
                        f"Product {item_payload.product_id} not found."
                    )
            # Replace items
            for old_item in list(sr.items):
                await self._session.delete(old_item)
            await self._session.flush()

            for item_payload in payload.items:
                item = StockReleaseItem(
                    stock_release_id=sr.id,
                    product_id=item_payload.product_id,
                    quantity_requested=item_payload.quantity_requested,
                    unit_cost=0,
                    line_total=0,
                    notes=item_payload.notes,
                )
                self._session.add(item)

        self._session.add(sr)
        await self._session.flush()

        await self._audit.log(
            actor_id=actor.id,
            action="stock_release:update",
            resource_type="stock_releases",
            resource_id=str(sr_id),
            ip_address=ip_address,
            status="success",
        )

        return await self._sr.get_active(sr_id)  # type: ignore[return-value]

    async def delete(
        self,
        sr_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        """Soft-delete a DRAFT stock release."""
        sr = await self.get(sr_id)
        if sr.status not in _SR_EDITABLE:
            raise ValidationError(
                f"Cannot delete a stock release in '{sr.status}' status. "
                "Only DRAFT releases can be deleted."
            )
        sr.is_deleted = True
        sr.deleted_at = _now()
        self._session.add(sr)
        await self._session.flush()

        await self._audit.log(
            actor_id=actor.id,
            action="stock_release:delete",
            resource_type="stock_releases",
            resource_id=str(sr_id),
            ip_address=ip_address,
            status="success",
        )

    # ------------------------------------------------------------------
    # Workflow transitions
    # ------------------------------------------------------------------

    async def submit(
        self,
        sr_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockRelease:
        """Submit a DRAFT release for approval."""
        sr = await self.get(sr_id)
        if sr.status not in _SR_SUBMITTABLE:
            raise ValidationError(
                f"Cannot submit a stock release in '{sr.status}' status."
            )
        if not sr.items:
            raise ValidationError("Cannot submit a stock release with no items.")

        sr.status = StockReleaseStatus.SUBMITTED
        sr.submitted_by_id = actor.id
        sr.submitted_at = _now()
        self._session.add(sr)
        await self._session.flush()

        await self._audit.log(
            actor_id=actor.id,
            action="stock_release:submit",
            resource_type="stock_releases",
            resource_id=str(sr_id),
            ip_address=ip_address,
            status="success",
        )

        await ws_manager.broadcast_json(
            make_event(
                EventType.STOCK_RELEASE_SUBMITTED,
                {
                    "id": str(sr_id),
                    "release_number": sr.release_number,
                    "submitted_by": actor.full_name,
                },
            )
        )

        # Auto-notification: notify admins of pending approval
        try:
            from app.services.notification import NotificationEventService

            notifier = NotificationEventService(self._session)
            await notifier.notify_stock_release_submitted(sr.release_number, sr_id, actor)
        except Exception:  # noqa: BLE001
            logger.warning("Stock release submit notification failed", sr_id=str(sr_id))

        return await self._sr.get_active(sr_id)  # type: ignore[return-value]

    async def approve(
        self,
        sr_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockRelease:
        """
        Approve a SUBMITTED stock release.

        For each item:
        1. Validate sufficient inventory exists.
        2. Deduct inventory atomically.
        3. Create an immutable InventoryLedgerEntry.
        4. Trigger low-stock / out-of-stock alerts if thresholds crossed.
        """
        sr = await self.get(sr_id)
        if sr.status not in _SR_APPROVABLE:
            raise ValidationError(
                f"Cannot approve a stock release in '{sr.status}' status."
            )

        # Pre-validate: check all items have sufficient stock BEFORE deducting any
        for item in sr.items:
            inv = await self._inv.get_by_product(item.product_id)
            available = float(inv.quantity_on_hand) if inv else 0.0
            requested = float(item.quantity_requested)
            if available < requested:
                product = item.product
                sku = product.sku if product else str(item.product_id)
                raise ValidationError(
                    f"Insufficient stock for product '{sku}'. "
                    f"Available: {available}, Requested: {requested}."
                )

        total_quantity = 0.0
        total_cost = 0.0

        inv_svc = InventoryService(self._session)

        # Apply deductions
        for item in sr.items:
            inv = await self._inv.get_or_create(item.product_id)
            unit_cost = float(inv.average_cost)
            qty = float(item.quantity_requested)

            entry = await _apply_inventory_change(
                inv,
                qty_change=-qty,
                unit_cost=unit_cost,
                inventory_repo=self._inv,
                ledger_repo=self._ledger,
                entry_type=LedgerEntryType.STOCK_RELEASE,
                reference_type=LedgerReferenceType.STOCK_RELEASE,
                reference_id=sr.id,
                reference_number=sr.release_number,
                notes=item.notes or f"Stock release: {sr.release_number}",
                created_by_id=actor.id,
            )

            # Update item with actual cost at time of release
            item.unit_cost = unit_cost
            item.line_total = round(qty * unit_cost, 4)
            self._session.add(item)

            total_quantity += qty
            total_cost += item.line_total

            # Broadcast per-product inventory decrease
            product = inv.product
            await ws_manager.broadcast_json(
                make_event(
                    EventType.INVENTORY_DECREASED,
                    {
                        "product_id": str(item.product_id),
                        "product_name": product.name if product else "",
                        "sku": product.sku if product else "",
                        "quantity_change": -qty,
                        "quantity_after": float(inv.quantity_on_hand),
                        "reference_type": "STOCK_RELEASE",
                        "reference_number": sr.release_number,
                    },
                )
            )

            # Trigger low-stock / out-of-stock alerts
            await inv_svc._publish_stock_alerts(inv)

        # Finalise the release document
        sr.total_quantity = round(total_quantity, 4)
        sr.total_cost = round(total_cost, 4)
        sr.status = StockReleaseStatus.APPROVED
        sr.approved_by_id = actor.id
        sr.approved_at = _now()
        self._session.add(sr)
        await self._session.flush()

        await self._audit.log(
            actor_id=actor.id,
            action="stock_release:approve",
            resource_type="stock_releases",
            resource_id=str(sr_id),
            ip_address=ip_address,
            status="success",
            new_values={
                "total_quantity": total_quantity,
                "total_cost": total_cost,
            },
        )

        await ws_manager.broadcast_json(
            make_event(
                EventType.STOCK_RELEASE_APPROVED,
                {
                    "id": str(sr_id),
                    "release_number": sr.release_number,
                    "approved_by": actor.full_name,
                    "total_quantity": total_quantity,
                    "total_cost": total_cost,
                },
            )
        )

        # Auto-notification: notify requester of approval
        try:
            from app.services.notification import NotificationEventService

            notifier = NotificationEventService(self._session)
            if sr.created_by_id:
                await notifier.notify_stock_release_approved(
                    sr.release_number, sr_id, actor, sr.created_by_id
                )
        except Exception:  # noqa: BLE001
            logger.warning("Stock release approve notification failed", sr_id=str(sr_id))

        return await self._sr.get_active(sr_id)  # type: ignore[return-value]

    async def cancel(
        self,
        sr_id: uuid.UUID,
        reason: str,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> StockRelease:
        """Cancel a DRAFT or SUBMITTED stock release. No inventory impact."""
        sr = await self.get(sr_id)
        if sr.status not in _SR_CANCELLABLE:
            raise ValidationError(
                f"Cannot cancel a stock release in '{sr.status}' status."
            )

        sr.status = StockReleaseStatus.CANCELLED
        sr.cancelled_by_id = actor.id
        sr.cancelled_at = _now()
        sr.cancellation_reason = reason
        self._session.add(sr)
        await self._session.flush()

        await self._audit.log(
            actor_id=actor.id,
            action="stock_release:cancel",
            resource_type="stock_releases",
            resource_id=str(sr_id),
            ip_address=ip_address,
            status="success",
            new_values={"reason": reason},
        )

        await ws_manager.broadcast_json(
            make_event(
                EventType.STOCK_RELEASE_CANCELLED,
                {
                    "id": str(sr_id),
                    "release_number": sr.release_number,
                    "cancelled_by": actor.full_name,
                    "reason": reason,
                },
            )
        )

        # Auto-notification: notify requester of cancellation
        try:
            from app.services.notification import NotificationEventService

            notifier = NotificationEventService(self._session)
            if sr.created_by_id:
                await notifier.notify_stock_release_cancelled(
                    sr.release_number, sr_id, actor, sr.created_by_id
                )
        except Exception:  # noqa: BLE001
            logger.warning("Stock release cancel notification failed", sr_id=str(sr_id))

        return await self._sr.get_active(sr_id)  # type: ignore[return-value]

    async def get_for_report(
        self,
        *,
        status: str | None = None,
        purpose: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[StockRelease]:
        return await self._sr.get_for_report(
            status=status,
            purpose=purpose,
            from_date=from_date,
            to_date=to_date,
        )


# ---------------------------------------------------------------------------
# StockReleaseDashboardService
# ---------------------------------------------------------------------------


class StockReleaseDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sr = StockReleaseRepository(session)

    async def get_summary(self) -> dict:
        """Compute stock-release KPIs for the dashboard."""
        from datetime import timedelta

        now = _now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        todays_releases = await self._sr.count_approved_today(today_start, today_end)
        todays_qty = await self._sr.sum_quantity_approved_today(today_start, today_end)
        monthly_qty = await self._sr.sum_quantity_approved_since(month_start)
        pending_releases = await self._sr.count_by_status(StockReleaseStatus.SUBMITTED)
        recent = await self._sr.get_recent_approved(limit=10)
        top_products = await self._sr.get_top_released_products(limit=5)

        # Enrich recent releases with product names from loaded items
        recent_releases = []
        for sr in recent:
            recent_releases.append(
                {
                    "id": str(sr.id),
                    "release_number": sr.release_number,
                    "purpose": sr.purpose,
                    "total_quantity": float(sr.total_quantity),
                    "total_cost": float(sr.total_cost),
                    "approved_at": sr.approved_at.isoformat() if sr.approved_at else None,
                    "created_by": (
                        sr.created_by.full_name if sr.created_by else None
                    ),
                }
            )

        return {
            "todays_releases": todays_releases,
            "todays_released_quantity": todays_qty,
            "monthly_released_quantity": monthly_qty,
            "pending_releases": pending_releases,
            "recent_releases": recent_releases,
            "top_released_products": top_products,
        }
