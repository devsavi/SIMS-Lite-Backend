"""
Master data repositories — Phase 2.

Domain-specific database queries for categories, brands, UoMs,
suppliers, and products.  All methods are async and follow the
project's BaseRepository pattern.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.master_data import Brand, Category, Product, Supplier, UnitOfMeasure
from app.repositories.base import BaseRepository


# ---------------------------------------------------------------------------
# CategoryRepository
# ---------------------------------------------------------------------------


class CategoryRepository(BaseRepository[Category]):
    model = Category

    async def get_active(self, pk: uuid.UUID) -> Category | None:
        """Fetch a non-deleted category by pk."""
        result = await self.session.execute(
            select(Category).where(
                and_(Category.id == pk, Category.is_deleted.is_(False))
            )
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Category | None:
        result = await self.session.execute(
            select(Category).where(
                and_(Category.slug == slug, Category.is_deleted.is_(False))
            )
        )
        return result.scalar_one_or_none()

    async def slug_exists(self, slug: str, exclude_id: uuid.UUID | None = None) -> bool:
        query = select(exists().where(
            and_(Category.slug == slug, Category.is_deleted.is_(False))
        ))
        if exclude_id:
            query = select(exists().where(
                and_(
                    Category.slug == slug,
                    Category.is_deleted.is_(False),
                    Category.id != exclude_id,
                )
            ))
        result = await self.session.execute(query)
        return bool(result.scalar())

    async def name_exists_in_parent(
        self,
        name: str,
        parent_id: uuid.UUID | None,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        conditions = [
            Category.name == name,
            Category.is_deleted.is_(False),
        ]
        if parent_id is None:
            conditions.append(Category.parent_id.is_(None))
        else:
            conditions.append(Category.parent_id == parent_id)
        if exclude_id:
            conditions.append(Category.id != exclude_id)
        result = await self.session.execute(
            select(exists().where(and_(*conditions)))
        )
        return bool(result.scalar())

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        active_only: bool = False,
        parent_id: uuid.UUID | None = None,
        include_parent_filter: bool = False,
    ) -> tuple[list[Category], int]:
        base_query = select(Category).where(Category.is_deleted.is_(False))

        if active_only:
            base_query = base_query.where(Category.is_active.is_(True))
        if include_parent_filter:
            if parent_id is None:
                base_query = base_query.where(Category.parent_id.is_(None))
            else:
                base_query = base_query.where(Category.parent_id == parent_id)
        if search:
            base_query = base_query.where(
                Category.name.ilike(f"%{search}%")
            )

        count_q = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        rows = await self.session.execute(
            base_query.order_by(Category.name.asc()).offset(offset).limit(limit)
        )
        return list(rows.scalars().all()), total


# ---------------------------------------------------------------------------
# BrandRepository
# ---------------------------------------------------------------------------


class BrandRepository(BaseRepository[Brand]):
    model = Brand

    async def get_active(self, pk: uuid.UUID) -> Brand | None:
        result = await self.session.execute(
            select(Brand).where(
                and_(Brand.id == pk, Brand.is_deleted.is_(False))
            )
        )
        return result.scalar_one_or_none()

    async def name_exists(self, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Brand.name == name, Brand.is_deleted.is_(False)]
        if exclude_id:
            conditions.append(Brand.id != exclude_id)
        result = await self.session.execute(
            select(exists().where(and_(*conditions)))
        )
        return bool(result.scalar())

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        active_only: bool = False,
    ) -> tuple[list[Brand], int]:
        base_query = select(Brand).where(Brand.is_deleted.is_(False))
        if active_only:
            base_query = base_query.where(Brand.is_active.is_(True))
        if search:
            base_query = base_query.where(Brand.name.ilike(f"%{search}%"))

        count_q = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()
        rows = await self.session.execute(
            base_query.order_by(Brand.name.asc()).offset(offset).limit(limit)
        )
        return list(rows.scalars().all()), total


# ---------------------------------------------------------------------------
# UnitOfMeasureRepository
# ---------------------------------------------------------------------------


class UnitOfMeasureRepository(BaseRepository[UnitOfMeasure]):
    model = UnitOfMeasure

    async def get_active(self, pk: uuid.UUID) -> UnitOfMeasure | None:
        result = await self.session.execute(
            select(UnitOfMeasure).where(
                and_(UnitOfMeasure.id == pk, UnitOfMeasure.is_deleted.is_(False))
            )
        )
        return result.scalar_one_or_none()

    async def name_exists(self, name: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [UnitOfMeasure.name == name, UnitOfMeasure.is_deleted.is_(False)]
        if exclude_id:
            conditions.append(UnitOfMeasure.id != exclude_id)
        result = await self.session.execute(
            select(exists().where(and_(*conditions)))
        )
        return bool(result.scalar())

    async def symbol_exists(self, symbol: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [UnitOfMeasure.symbol == symbol, UnitOfMeasure.is_deleted.is_(False)]
        if exclude_id:
            conditions.append(UnitOfMeasure.id != exclude_id)
        result = await self.session.execute(
            select(exists().where(and_(*conditions)))
        )
        return bool(result.scalar())

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        active_only: bool = False,
    ) -> tuple[list[UnitOfMeasure], int]:
        base_query = select(UnitOfMeasure).where(UnitOfMeasure.is_deleted.is_(False))
        if active_only:
            base_query = base_query.where(UnitOfMeasure.is_active.is_(True))
        if search:
            base_query = base_query.where(
                or_(
                    UnitOfMeasure.name.ilike(f"%{search}%"),
                    UnitOfMeasure.symbol.ilike(f"%{search}%"),
                )
            )
        count_q = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()
        rows = await self.session.execute(
            base_query.order_by(UnitOfMeasure.name.asc()).offset(offset).limit(limit)
        )
        return list(rows.scalars().all()), total


# ---------------------------------------------------------------------------
# SupplierRepository
# ---------------------------------------------------------------------------


class SupplierRepository(BaseRepository[Supplier]):
    model = Supplier

    async def get_active(self, pk: uuid.UUID) -> Supplier | None:
        result = await self.session.execute(
            select(Supplier).where(
                and_(Supplier.id == pk, Supplier.is_deleted.is_(False))
            )
        )
        return result.scalar_one_or_none()

    async def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [
            Supplier.supplier_code == code,
            Supplier.is_deleted.is_(False),
        ]
        if exclude_id:
            conditions.append(Supplier.id != exclude_id)
        result = await self.session.execute(
            select(exists().where(and_(*conditions)))
        )
        return bool(result.scalar())

    async def get_next_code(self) -> str:
        """Generate the next sequential supplier code (SUP-XXXXX)."""
        result = await self.session.execute(
            select(func.count()).select_from(Supplier)
        )
        count = result.scalar_one()
        return f"SUP-{(count + 1):05d}"

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        active_only: bool = False,
    ) -> tuple[list[Supplier], int]:
        base_query = select(Supplier).where(Supplier.is_deleted.is_(False))
        if active_only:
            base_query = base_query.where(Supplier.is_active.is_(True))
        if search:
            base_query = base_query.where(
                or_(
                    Supplier.name.ilike(f"%{search}%"),
                    Supplier.supplier_code.ilike(f"%{search}%"),
                    Supplier.email.ilike(f"%{search}%"),
                    Supplier.contact_person.ilike(f"%{search}%"),
                )
            )
        count_q = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()
        rows = await self.session.execute(
            base_query.order_by(Supplier.name.asc()).offset(offset).limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_all_active(self) -> list[Supplier]:
        """Return all active non-deleted suppliers (for reports)."""
        rows = await self.session.execute(
            select(Supplier)
            .where(and_(Supplier.is_deleted.is_(False), Supplier.is_active.is_(True)))
            .order_by(Supplier.name.asc())
        )
        return list(rows.scalars().all())


# ---------------------------------------------------------------------------
# ProductRepository
# ---------------------------------------------------------------------------


class ProductRepository(BaseRepository[Product]):
    model = Product

    _eager_options = [
        selectinload(Product.category),
        selectinload(Product.brand),
        selectinload(Product.uom),
        selectinload(Product.supplier),
    ]

    async def get_active(self, pk: uuid.UUID) -> Product | None:
        result = await self.session.execute(
            select(Product)
            .where(and_(Product.id == pk, Product.is_deleted.is_(False)))
            .options(*self._eager_options)
        )
        return result.scalar_one_or_none()

    async def sku_exists(self, sku: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Product.sku == sku, Product.is_deleted.is_(False)]
        if exclude_id:
            conditions.append(Product.id != exclude_id)
        result = await self.session.execute(
            select(exists().where(and_(*conditions)))
        )
        return bool(result.scalar())

    async def barcode_exists(self, barcode: str, exclude_id: uuid.UUID | None = None) -> bool:
        conditions = [Product.barcode == barcode, Product.is_deleted.is_(False)]
        if exclude_id:
            conditions.append(Product.id != exclude_id)
        result = await self.session.execute(
            select(exists().where(and_(*conditions)))
        )
        return bool(result.scalar())

    async def get_next_sku_sequence(self, prefix: str) -> int:
        """Return the count of products matching a SKU prefix for sequence generation."""
        result = await self.session.execute(
            select(func.count()).select_from(Product).where(
                Product.sku.like(f"{prefix}%")
            )
        )
        return result.scalar_one()

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        search: str | None = None,
        active_only: bool = False,
        category_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
    ) -> tuple[list[Product], int]:
        base_query = (
            select(Product)
            .where(Product.is_deleted.is_(False))
            .options(*self._eager_options)
        )
        if active_only:
            base_query = base_query.where(Product.is_active.is_(True))
        if category_id:
            base_query = base_query.where(Product.category_id == category_id)
        if brand_id:
            base_query = base_query.where(Product.brand_id == brand_id)
        if supplier_id:
            base_query = base_query.where(Product.supplier_id == supplier_id)
        if search:
            base_query = base_query.where(
                or_(
                    Product.name.ilike(f"%{search}%"),
                    Product.sku.ilike(f"%{search}%"),
                    Product.barcode.ilike(f"%{search}%"),
                    Product.description.ilike(f"%{search}%"),
                )
            )

        count_q = select(func.count()).select_from(
            base_query.options().subquery()
        )
        total = (await self.session.execute(count_q)).scalar_one()
        rows = await self.session.execute(
            base_query.order_by(Product.name.asc()).offset(offset).limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_all_for_report(
        self,
        *,
        active_only: bool = False,
        category_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
    ) -> list[Product]:
        """Return all matching products (no pagination) for report generation."""
        base_query = (
            select(Product)
            .where(Product.is_deleted.is_(False))
            .options(*self._eager_options)
        )
        if active_only:
            base_query = base_query.where(Product.is_active.is_(True))
        if category_id:
            base_query = base_query.where(Product.category_id == category_id)
        if supplier_id:
            base_query = base_query.where(Product.supplier_id == supplier_id)
        rows = await self.session.execute(base_query.order_by(Product.name.asc()))
        return list(rows.scalars().all())
