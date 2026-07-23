"""
Inventory repositories — Phase 4.

Domain-specific database queries for Inventory, InventoryLedgerEntry,
and StockAdjustment.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory import (
    Inventory,
    InventoryLedgerEntry,
    StockAdjustment,
    StockAdjustmentItem,
    StockAdjustmentStatus,
)
from app.models.master_data import Product
from app.repositories.base import BaseRepository


# ---------------------------------------------------------------------------
# InventoryRepository
# ---------------------------------------------------------------------------


class InventoryRepository(BaseRepository[Inventory]):
    model = Inventory

    _eager_options = [
        selectinload(Inventory.product),
    ]

    async def get_by_product(self, product_id: uuid.UUID) -> Inventory | None:
        """Return the inventory row for a given product, or None."""
        result = await self.session.execute(
            select(Inventory)
            .where(Inventory.product_id == product_id)
            .options(*self._eager_options)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, product_id: uuid.UUID) -> Inventory:
        """Return or create the inventory row for a product."""
        inv = await self.get_by_product(product_id)
        if inv is None:
            inv = Inventory(
                product_id=product_id,
                quantity_on_hand=0,
                average_cost=0,
            )
            self.session.add(inv)
            await self.session.flush()
            await self.session.refresh(inv)
        return inv

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        category_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        low_stock_only: bool = False,
        out_of_stock_only: bool = False,
    ) -> tuple[list[Inventory], int]:
        """Return a paginated list of inventory rows with optional filters."""
        base_query = (
            select(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .where(Product.is_deleted.is_(False))
            .where(Product.is_active.is_(True))
            .options(*self._eager_options)
        )

        if search:
            base_query = base_query.where(
                or_(
                    Product.name.ilike(f"%{search}%"),
                    Product.sku.ilike(f"%{search}%"),
                    Product.barcode.ilike(f"%{search}%"),
                )
            )
        if category_id:
            base_query = base_query.where(Product.category_id == category_id)
        if supplier_id:
            base_query = base_query.where(Product.supplier_id == supplier_id)
        if out_of_stock_only:
            base_query = base_query.where(Inventory.quantity_on_hand <= 0)
        elif low_stock_only:
            # low stock: qty > 0 but <= reorder_level
            base_query = base_query.where(
                and_(
                    Inventory.quantity_on_hand > 0,
                    Inventory.quantity_on_hand <= Product.reorder_level,
                    Product.reorder_level > 0,
                )
            )

        count_q = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        rows = await self.session.execute(
            base_query.order_by(Product.name.asc()).offset(offset).limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_all_for_report(
        self,
        *,
        category_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        low_stock_only: bool = False,
        out_of_stock_only: bool = False,
    ) -> list[Inventory]:
        """Return all inventory rows for report generation (no pagination)."""
        base_query = (
            select(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .where(Product.is_deleted.is_(False))
            .where(Product.is_active.is_(True))
            .options(*self._eager_options)
        )
        if category_id:
            base_query = base_query.where(Product.category_id == category_id)
        if supplier_id:
            base_query = base_query.where(Product.supplier_id == supplier_id)
        if out_of_stock_only:
            base_query = base_query.where(Inventory.quantity_on_hand <= 0)
        elif low_stock_only:
            base_query = base_query.where(
                and_(
                    Inventory.quantity_on_hand > 0,
                    Inventory.quantity_on_hand <= Product.reorder_level,
                    Product.reorder_level > 0,
                )
            )
        rows = await self.session.execute(
            base_query.order_by(Product.name.asc())
        )
        return list(rows.scalars().all())

    async def get_summary(self) -> dict:
        """Compute summary statistics for the inventory dashboard."""
        # Total active products
        total_products_result = await self.session.execute(
            select(func.count())
            .select_from(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .where(Product.is_deleted.is_(False))
            .where(Product.is_active.is_(True))
        )
        total_products = total_products_result.scalar_one()

        # Products with qty > 0
        in_stock_result = await self.session.execute(
            select(func.count())
            .select_from(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .where(Product.is_deleted.is_(False))
            .where(Product.is_active.is_(True))
            .where(Inventory.quantity_on_hand > 0)
        )
        in_stock = in_stock_result.scalar_one()

        # Out of stock
        out_of_stock = total_products - in_stock

        # Low stock (qty > 0 and qty <= reorder_level, reorder_level > 0)
        low_stock_result = await self.session.execute(
            select(func.count())
            .select_from(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .where(Product.is_deleted.is_(False))
            .where(Product.is_active.is_(True))
            .where(Inventory.quantity_on_hand > 0)
            .where(Inventory.quantity_on_hand <= Product.reorder_level)
            .where(Product.reorder_level > 0)
        )
        low_stock = low_stock_result.scalar_one()

        # Total qty on hand
        total_qty_result = await self.session.execute(
            select(func.coalesce(func.sum(Inventory.quantity_on_hand), 0))
            .select_from(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .where(Product.is_deleted.is_(False))
            .where(Product.is_active.is_(True))
        )
        total_qty = float(total_qty_result.scalar_one())

        # Total stock value (qty * avg_cost)
        total_value_result = await self.session.execute(
            select(
                func.coalesce(
                    func.sum(Inventory.quantity_on_hand * Inventory.average_cost), 0
                )
            )
            .select_from(Inventory)
            .join(Product, Inventory.product_id == Product.id)
            .where(Product.is_deleted.is_(False))
            .where(Product.is_active.is_(True))
        )
        total_value = float(total_value_result.scalar_one())

        return {
            "total_products": total_products,
            "total_products_in_stock": in_stock,
            "total_out_of_stock": out_of_stock,
            "total_low_stock": low_stock,
            "total_quantity_on_hand": total_qty,
            "total_stock_value": round(total_value, 4),
        }


# ---------------------------------------------------------------------------
# InventoryLedgerEntryRepository
# ---------------------------------------------------------------------------


class InventoryLedgerEntryRepository(BaseRepository[InventoryLedgerEntry]):
    model = InventoryLedgerEntry

    _eager_options = [
        selectinload(InventoryLedgerEntry.product),
        selectinload(InventoryLedgerEntry.created_by),
    ]

    async def append(
        self,
        *,
        product_id: uuid.UUID,
        entry_type: str,
        quantity_before: float,
        quantity_change: float,
        quantity_after: float,
        unit_cost: float = 0,
        reference_type: str | None = None,
        reference_id: uuid.UUID | None = None,
        reference_number: str | None = None,
        notes: str | None = None,
        created_by_id: uuid.UUID | None = None,
    ) -> InventoryLedgerEntry:
        """Append a new immutable ledger entry."""
        entry = InventoryLedgerEntry(
            product_id=product_id,
            entry_type=entry_type,
            quantity_before=quantity_before,
            quantity_change=quantity_change,
            quantity_after=quantity_after,
            unit_cost=unit_cost,
            reference_type=reference_type,
            reference_id=reference_id,
            reference_number=reference_number,
            notes=notes,
            created_by_id=created_by_id,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def get_current_stock(self, product_id: uuid.UUID) -> float:
        """Return the latest quantity_after for a product (0.0 if none)."""
        result = await self.session.execute(
            select(InventoryLedgerEntry.quantity_after)
            .where(InventoryLedgerEntry.product_id == product_id)
            .order_by(InventoryLedgerEntry.created_at.desc())
            .limit(1)
        )
        val = result.scalar_one_or_none()
        return float(val) if val is not None else 0.0

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        product_id: uuid.UUID | None = None,
        entry_type: str | None = None,
        reference_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[InventoryLedgerEntry], int]:
        base_query = select(InventoryLedgerEntry).options(*self._eager_options)

        if product_id:
            base_query = base_query.where(
                InventoryLedgerEntry.product_id == product_id
            )
        if entry_type:
            base_query = base_query.where(
                InventoryLedgerEntry.entry_type == entry_type
            )
        if reference_type:
            base_query = base_query.where(
                InventoryLedgerEntry.reference_type == reference_type
            )
        if from_date:
            base_query = base_query.where(
                InventoryLedgerEntry.created_at >= from_date
            )
        if to_date:
            base_query = base_query.where(
                InventoryLedgerEntry.created_at <= to_date
            )

        count_q = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        rows = await self.session.execute(
            base_query.order_by(InventoryLedgerEntry.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_by_reference(
        self,
        reference_type: str,
        reference_id: uuid.UUID,
    ) -> list[InventoryLedgerEntry]:
        """Return all ledger entries for a given reference document."""
        rows = await self.session.execute(
            select(InventoryLedgerEntry)
            .where(
                and_(
                    InventoryLedgerEntry.reference_type == reference_type,
                    InventoryLedgerEntry.reference_id == reference_id,
                )
            )
            .options(*self._eager_options)
            .order_by(InventoryLedgerEntry.created_at.asc())
        )
        return list(rows.scalars().all())

    async def get_for_product_paginated(
        self,
        product_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[InventoryLedgerEntry], int]:
        query = (
            select(InventoryLedgerEntry)
            .where(InventoryLedgerEntry.product_id == product_id)
            .options(*self._eager_options)
        )
        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()
        rows = await self.session.execute(
            query.order_by(InventoryLedgerEntry.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_all_for_report(
        self,
        *,
        product_id: uuid.UUID | None = None,
        entry_type: str | None = None,
        reference_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[InventoryLedgerEntry]:
        base_query = select(InventoryLedgerEntry).options(*self._eager_options)
        if product_id:
            base_query = base_query.where(
                InventoryLedgerEntry.product_id == product_id
            )
        if entry_type:
            base_query = base_query.where(
                InventoryLedgerEntry.entry_type == entry_type
            )
        if reference_type:
            base_query = base_query.where(
                InventoryLedgerEntry.reference_type == reference_type
            )
        if from_date:
            base_query = base_query.where(
                InventoryLedgerEntry.created_at >= from_date
            )
        if to_date:
            base_query = base_query.where(
                InventoryLedgerEntry.created_at <= to_date
            )
        rows = await self.session.execute(
            base_query.order_by(InventoryLedgerEntry.created_at.desc())
        )
        return list(rows.scalars().all())


# ---------------------------------------------------------------------------
# StockAdjustmentRepository
# ---------------------------------------------------------------------------


class StockAdjustmentRepository(BaseRepository[StockAdjustment]):
    model = StockAdjustment

    _eager_options = [
        selectinload(StockAdjustment.items).selectinload(StockAdjustmentItem.product),
        selectinload(StockAdjustment.created_by),
        selectinload(StockAdjustment.submitted_by),
        selectinload(StockAdjustment.approved_by),
        selectinload(StockAdjustment.cancelled_by),
    ]

    async def get_active(self, pk: uuid.UUID) -> StockAdjustment | None:
        result = await self.session.execute(
            select(StockAdjustment)
            .where(
                and_(
                    StockAdjustment.id == pk,
                    StockAdjustment.is_deleted.is_(False),
                )
            )
            .options(*self._eager_options)
        )
        return result.scalar_one_or_none()

    async def get_next_adjustment_number(self) -> str:
        """Generate next sequential adjustment number (ADJ-YYYYMMDD-XXXXX)."""
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"ADJ-{today}-"
        result = await self.session.execute(
            select(func.count())
            .select_from(StockAdjustment)
            .where(StockAdjustment.adjustment_number.like(f"{prefix}%"))
        )
        count = result.scalar_one()
        return f"{prefix}{count + 1:05d}"

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        status: str | None = None,
        adjustment_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[StockAdjustment], int]:
        base_query = (
            select(StockAdjustment)
            .where(StockAdjustment.is_deleted.is_(False))
            .options(*self._eager_options)
        )
        if status:
            base_query = base_query.where(StockAdjustment.status == status)
        if adjustment_type:
            base_query = base_query.where(
                StockAdjustment.adjustment_type == adjustment_type
            )
        if from_date:
            base_query = base_query.where(StockAdjustment.created_at >= from_date)
        if to_date:
            base_query = base_query.where(StockAdjustment.created_at <= to_date)
        if search:
            base_query = base_query.where(
                StockAdjustment.adjustment_number.ilike(f"%{search}%")
            )

        count_q = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        rows = await self.session.execute(
            base_query.order_by(StockAdjustment.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_for_report(
        self,
        *,
        status: str | None = None,
        adjustment_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[StockAdjustment]:
        base_query = (
            select(StockAdjustment)
            .where(StockAdjustment.is_deleted.is_(False))
            .options(*self._eager_options)
        )
        if status:
            base_query = base_query.where(StockAdjustment.status == status)
        if adjustment_type:
            base_query = base_query.where(
                StockAdjustment.adjustment_type == adjustment_type
            )
        if from_date:
            base_query = base_query.where(StockAdjustment.created_at >= from_date)
        if to_date:
            base_query = base_query.where(StockAdjustment.created_at <= to_date)
        rows = await self.session.execute(
            base_query.order_by(StockAdjustment.created_at.desc())
        )
        return list(rows.scalars().all())

    async def count_by_status(self, status: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(StockAdjustment)
            .where(
                and_(
                    StockAdjustment.status == status,
                    StockAdjustment.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one()

    async def get_recent_activities(self, limit: int = 10) -> list[StockAdjustment]:
        rows = await self.session.execute(
            select(StockAdjustment)
            .where(StockAdjustment.is_deleted.is_(False))
            .options(*self._eager_options)
            .order_by(StockAdjustment.updated_at.desc())
            .limit(limit)
        )
        return list(rows.scalars().all())
