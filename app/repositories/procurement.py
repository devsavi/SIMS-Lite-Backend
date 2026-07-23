"""
Procurement repositories — Phase 3.

Domain-specific database queries for PurchaseOrder, GRN, and InventoryLedger.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.procurement import (
    GRN,
    GRNItem,
    GRNStatus,
    InventoryLedger,
    POStatus,
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.repositories.base import BaseRepository


# ---------------------------------------------------------------------------
# PurchaseOrderRepository
# ---------------------------------------------------------------------------


class PurchaseOrderRepository(BaseRepository[PurchaseOrder]):
    model = PurchaseOrder

    _eager_options = [
        selectinload(PurchaseOrder.supplier),
        selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.product),
        selectinload(PurchaseOrder.created_by),
        selectinload(PurchaseOrder.submitted_by),
        selectinload(PurchaseOrder.approved_by),
        selectinload(PurchaseOrder.rejected_by),
        selectinload(PurchaseOrder.cancelled_by),
    ]

    async def get_active(self, pk: uuid.UUID) -> PurchaseOrder | None:
        result = await self.session.execute(
            select(PurchaseOrder)
            .where(
                and_(
                    PurchaseOrder.id == pk,
                    PurchaseOrder.is_deleted.is_(False),
                )
            )
            .options(*self._eager_options)
        )
        return result.scalar_one_or_none()

    async def get_next_po_number(self) -> str:
        """Generate next sequential PO number (PO-YYYYMMDD-XXXXX)."""
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"PO-{today}-"
        result = await self.session.execute(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.po_number.like(f"{prefix}%"))
        )
        count = result.scalar_one()
        return f"{prefix}{count + 1:05d}"

    async def po_number_exists(self, po_number: str) -> bool:
        result = await self.session.execute(
            select(exists().where(PurchaseOrder.po_number == po_number))
        )
        return bool(result.scalar())

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        status: str | None = None,
        supplier_id: uuid.UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[PurchaseOrder], int]:
        base_query = (
            select(PurchaseOrder)
            .where(PurchaseOrder.is_deleted.is_(False))
            .options(*self._eager_options)
        )
        if status:
            base_query = base_query.where(PurchaseOrder.status == status)
        if supplier_id:
            base_query = base_query.where(PurchaseOrder.supplier_id == supplier_id)
        if from_date:
            base_query = base_query.where(PurchaseOrder.order_date >= from_date)
        if to_date:
            base_query = base_query.where(PurchaseOrder.order_date <= to_date)
        if search:
            base_query = base_query.where(
                PurchaseOrder.po_number.ilike(f"%{search}%")
            )

        count_q = select(func.count()).select_from(
            base_query.options().subquery()
        )
        total = (await self.session.execute(count_q)).scalar_one()
        rows = await self.session.execute(
            base_query.order_by(PurchaseOrder.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_for_report(
        self,
        *,
        supplier_id: uuid.UUID | None = None,
        status: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[PurchaseOrder]:
        base_query = (
            select(PurchaseOrder)
            .where(PurchaseOrder.is_deleted.is_(False))
            .options(*self._eager_options)
        )
        if supplier_id:
            base_query = base_query.where(PurchaseOrder.supplier_id == supplier_id)
        if status:
            base_query = base_query.where(PurchaseOrder.status == status)
        if from_date:
            base_query = base_query.where(PurchaseOrder.order_date >= from_date)
        if to_date:
            base_query = base_query.where(PurchaseOrder.order_date <= to_date)
        rows = await self.session.execute(
            base_query.order_by(PurchaseOrder.order_date.desc())
        )
        return list(rows.scalars().all())

    async def count_by_status(self, status: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(
                and_(
                    PurchaseOrder.status == status,
                    PurchaseOrder.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one()

    async def sum_total_by_date_range(
        self,
        from_date: datetime,
        to_date: datetime,
        status: str | None = None,
    ) -> float:
        query = select(func.coalesce(func.sum(PurchaseOrder.total_amount), 0)).where(
            and_(
                PurchaseOrder.is_deleted.is_(False),
                PurchaseOrder.order_date >= from_date,
                PurchaseOrder.order_date <= to_date,
            )
        )
        if status:
            query = query.where(PurchaseOrder.status == status)
        result = await self.session.execute(query)
        return float(result.scalar_one())

    async def sum_total_all(self) -> float:
        result = await self.session.execute(
            select(func.coalesce(func.sum(PurchaseOrder.total_amount), 0)).where(
                PurchaseOrder.is_deleted.is_(False)
            )
        )
        return float(result.scalar_one())

    async def count_approved_since(self, from_date: datetime) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(
                and_(
                    PurchaseOrder.status.in_(
                        [
                            POStatus.APPROVED,
                            POStatus.PARTIALLY_RECEIVED,
                            POStatus.FULLY_RECEIVED,
                        ]
                    ),
                    PurchaseOrder.approved_at >= from_date,
                    PurchaseOrder.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one()

    async def get_recent_activities(self, limit: int = 10) -> list[PurchaseOrder]:
        rows = await self.session.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.is_deleted.is_(False))
            .options(selectinload(PurchaseOrder.supplier))
            .order_by(PurchaseOrder.updated_at.desc())
            .limit(limit)
        )
        return list(rows.scalars().all())


# ---------------------------------------------------------------------------
# GRNRepository
# ---------------------------------------------------------------------------


class GRNRepository(BaseRepository[GRN]):
    model = GRN

    _eager_options = [
        selectinload(GRN.purchase_order).selectinload(PurchaseOrder.supplier),
        selectinload(GRN.items)
        .selectinload(GRNItem.product),
        selectinload(GRN.items)
        .selectinload(GRNItem.po_item),
        selectinload(GRN.created_by),
        selectinload(GRN.submitted_by),
        selectinload(GRN.approved_by),
        selectinload(GRN.cancelled_by),
    ]

    async def get_active(self, pk: uuid.UUID) -> GRN | None:
        result = await self.session.execute(
            select(GRN)
            .where(GRN.id == pk)
            .options(*self._eager_options)
        )
        return result.scalar_one_or_none()

    async def get_next_grn_number(self) -> str:
        """Generate next sequential GRN number (GRN-YYYYMMDD-XXXXX)."""
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"GRN-{today}-"
        result = await self.session.execute(
            select(func.count())
            .select_from(GRN)
            .where(GRN.grn_number.like(f"{prefix}%"))
        )
        count = result.scalar_one()
        return f"{prefix}{count + 1:05d}"

    async def get_by_po(self, po_id: uuid.UUID) -> list[GRN]:
        """All GRNs for a given PO."""
        rows = await self.session.execute(
            select(GRN)
            .where(GRN.purchase_order_id == po_id)
            .options(*self._eager_options)
            .order_by(GRN.created_at.asc())
        )
        return list(rows.scalars().all())

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        status: str | None = None,
        po_id: uuid.UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[GRN], int]:
        base_query = (
            select(GRN)
            .options(*self._eager_options)
        )
        if status:
            base_query = base_query.where(GRN.status == status)
        if po_id:
            base_query = base_query.where(GRN.purchase_order_id == po_id)
        if from_date:
            base_query = base_query.where(GRN.received_date >= from_date)
        if to_date:
            base_query = base_query.where(GRN.received_date <= to_date)
        if search:
            base_query = base_query.where(GRN.grn_number.ilike(f"%{search}%"))

        count_q = select(func.count()).select_from(base_query.options().subquery())
        total = (await self.session.execute(count_q)).scalar_one()
        rows = await self.session.execute(
            base_query.order_by(GRN.created_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_for_report(
        self,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        status: str | None = None,
    ) -> list[GRN]:
        base_query = select(GRN).options(*self._eager_options)
        if status:
            base_query = base_query.where(GRN.status == status)
        if from_date:
            base_query = base_query.where(GRN.received_date >= from_date)
        if to_date:
            base_query = base_query.where(GRN.received_date <= to_date)
        rows = await self.session.execute(
            base_query.order_by(GRN.received_date.desc())
        )
        return list(rows.scalars().all())

    async def count_by_status(self, status: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(GRN)
            .where(GRN.status == status)
        )
        return result.scalar_one()

    async def count_approved_since(self, from_date: datetime) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(GRN)
            .where(
                and_(
                    GRN.status == GRNStatus.APPROVED,
                    GRN.approved_at >= from_date,
                )
            )
        )
        return result.scalar_one()


# ---------------------------------------------------------------------------
# InventoryLedgerRepository
# ---------------------------------------------------------------------------


class InventoryLedgerRepository(BaseRepository[InventoryLedger]):
    model = InventoryLedger

    async def append(
        self,
        *,
        product_id: uuid.UUID,
        entry_type: str,
        quantity_before: float,
        quantity_change: float,
        quantity_after: float,
        unit_cost: float = 0,
        grn_id: uuid.UUID | None = None,
        reference_number: str | None = None,
        notes: str | None = None,
        created_by_id: uuid.UUID | None = None,
    ) -> InventoryLedger:
        entry = InventoryLedger(
            product_id=product_id,
            entry_type=entry_type,
            quantity_before=quantity_before,
            quantity_change=quantity_change,
            quantity_after=quantity_after,
            unit_cost=unit_cost,
            grn_id=grn_id,
            reference_number=reference_number,
            notes=notes,
            created_by_id=created_by_id,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def get_for_product(
        self,
        product_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[InventoryLedger], int]:
        query = (
            select(InventoryLedger)
            .where(InventoryLedger.product_id == product_id)
            .options(
                selectinload(InventoryLedger.product),
                selectinload(InventoryLedger.created_by),
            )
        )
        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()
        rows = await self.session.execute(
            query.order_by(InventoryLedger.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_current_stock(self, product_id: uuid.UUID) -> float:
        """
        Return the latest quantity_after for a product.
        Returns 0.0 if no ledger entries exist.
        """
        result = await self.session.execute(
            select(InventoryLedger.quantity_after)
            .where(InventoryLedger.product_id == product_id)
            .order_by(InventoryLedger.created_at.desc())
            .limit(1)
        )
        val = result.scalar_one_or_none()
        return float(val) if val is not None else 0.0
