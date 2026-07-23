"""
Stock Release repository — Phase 5.

Domain-specific database queries for StockRelease and StockReleaseItem.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.stock_release import StockRelease, StockReleaseItem, StockReleaseStatus
from app.repositories.base import BaseRepository


class StockReleaseRepository(BaseRepository[StockRelease]):
    model = StockRelease

    _eager_options = [
        selectinload(StockRelease.items).selectinload(StockReleaseItem.product),
        selectinload(StockRelease.created_by),
        selectinload(StockRelease.submitted_by),
        selectinload(StockRelease.approved_by),
        selectinload(StockRelease.cancelled_by),
    ]

    async def get_active(self, pk: uuid.UUID) -> StockRelease | None:
        result = await self.session.execute(
            select(StockRelease)
            .where(
                and_(
                    StockRelease.id == pk,
                    StockRelease.is_deleted.is_(False),
                )
            )
            .options(*self._eager_options)
        )
        return result.scalar_one_or_none()

    async def get_next_release_number(self) -> str:
        """Generate next sequential release number (SR-YYYYMMDD-XXXXX)."""
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"SR-{today}-"
        result = await self.session.execute(
            select(func.count())
            .select_from(StockRelease)
            .where(StockRelease.release_number.like(f"{prefix}%"))
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
        purpose: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[StockRelease], int]:
        base_query = (
            select(StockRelease)
            .where(StockRelease.is_deleted.is_(False))
            .options(*self._eager_options)
        )
        if status:
            base_query = base_query.where(StockRelease.status == status)
        if purpose:
            base_query = base_query.where(StockRelease.purpose == purpose)
        if from_date:
            base_query = base_query.where(StockRelease.release_date >= from_date)
        if to_date:
            base_query = base_query.where(StockRelease.release_date <= to_date)
        if search:
            base_query = base_query.where(
                StockRelease.release_number.ilike(f"%{search}%")
            )

        count_q = select(func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        rows = await self.session.execute(
            base_query.order_by(StockRelease.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    async def get_for_report(
        self,
        *,
        status: str | None = None,
        purpose: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[StockRelease]:
        base_query = (
            select(StockRelease)
            .where(StockRelease.is_deleted.is_(False))
            .options(*self._eager_options)
        )
        if status:
            base_query = base_query.where(StockRelease.status == status)
        if purpose:
            base_query = base_query.where(StockRelease.purpose == purpose)
        if from_date:
            base_query = base_query.where(StockRelease.release_date >= from_date)
        if to_date:
            base_query = base_query.where(StockRelease.release_date <= to_date)
        rows = await self.session.execute(
            base_query.order_by(StockRelease.release_date.desc())
        )
        return list(rows.scalars().all())

    async def count_by_status(self, status: str) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(StockRelease)
            .where(
                and_(
                    StockRelease.status == status,
                    StockRelease.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one()

    async def count_approved_today(self, date_start: datetime, date_end: datetime) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(StockRelease)
            .where(
                and_(
                    StockRelease.status == StockReleaseStatus.APPROVED,
                    StockRelease.approved_at >= date_start,
                    StockRelease.approved_at < date_end,
                    StockRelease.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one()

    async def sum_quantity_approved_today(
        self, date_start: datetime, date_end: datetime
    ) -> float:
        result = await self.session.execute(
            select(func.coalesce(func.sum(StockRelease.total_quantity), 0))
            .select_from(StockRelease)
            .where(
                and_(
                    StockRelease.status == StockReleaseStatus.APPROVED,
                    StockRelease.approved_at >= date_start,
                    StockRelease.approved_at < date_end,
                    StockRelease.is_deleted.is_(False),
                )
            )
        )
        return float(result.scalar_one())

    async def sum_quantity_approved_since(self, from_date: datetime) -> float:
        result = await self.session.execute(
            select(func.coalesce(func.sum(StockRelease.total_quantity), 0))
            .select_from(StockRelease)
            .where(
                and_(
                    StockRelease.status == StockReleaseStatus.APPROVED,
                    StockRelease.approved_at >= from_date,
                    StockRelease.is_deleted.is_(False),
                )
            )
        )
        return float(result.scalar_one())

    async def get_recent_approved(self, limit: int = 10) -> list[StockRelease]:
        rows = await self.session.execute(
            select(StockRelease)
            .where(
                and_(
                    StockRelease.status == StockReleaseStatus.APPROVED,
                    StockRelease.is_deleted.is_(False),
                )
            )
            .options(
                selectinload(StockRelease.created_by),
            )
            .order_by(StockRelease.approved_at.desc())
            .limit(limit)
        )
        return list(rows.scalars().all())

    async def get_top_released_products(self, limit: int = 5) -> list[dict]:
        """Return top N products by total released quantity (approved releases)."""
        from sqlalchemy import desc

        result = await self.session.execute(
            select(
                StockReleaseItem.product_id,
                func.sum(StockReleaseItem.quantity_requested).label("total_qty"),
                func.sum(StockReleaseItem.line_total).label("total_value"),
            )
            .join(StockRelease, StockRelease.id == StockReleaseItem.stock_release_id)
            .where(
                and_(
                    StockRelease.status == StockReleaseStatus.APPROVED,
                    StockRelease.is_deleted.is_(False),
                )
            )
            .group_by(StockReleaseItem.product_id)
            .order_by(desc("total_qty"))
            .limit(limit)
        )
        return [
            {
                "product_id": str(row.product_id),
                "total_quantity": float(row.total_qty),
                "total_value": float(row.total_value),
            }
            for row in result.all()
        ]
