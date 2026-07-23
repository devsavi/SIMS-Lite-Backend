"""
Master data reports endpoints -- Phase 2.

GET /api/v1/reports/products   -- Excel product report
GET /api/v1/reports/suppliers  -- Excel supplier report
GET /api/v1/reports/categories -- Excel category report
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.repositories.master_data import CategoryRepository, SupplierRepository
from app.services.master_data import ProductService
from app.services.report import ReportService

router = APIRouter()


def _report_svc() -> ReportService:
    return ReportService()


@router.get("/products", summary="Export product report as Excel", response_class=Response)
async def export_product_report(
    active_only: bool = Query(default=False),
    category_id: uuid.UUID | None = Query(default=None),
    supplier_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: ReportService = Depends(_report_svc),
) -> Response:
    svc = ProductService(db)
    products = await svc.get_for_report(
        active_only=active_only,
        category_id=category_id,
        supplier_id=supplier_id,
    )
    data = report_svc.generate_product_report(products)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=products_report.xlsx"},
    )


@router.get("/suppliers", summary="Export supplier report as Excel", response_class=Response)
async def export_supplier_report(
    active_only: bool = Query(default=False),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: ReportService = Depends(_report_svc),
) -> Response:
    repo = SupplierRepository(db)
    if active_only:
        suppliers = await repo.get_all_active()
    else:
        from sqlalchemy import and_, select
        from app.models.master_data import Supplier
        result = await db.execute(
            select(Supplier)
            .where(Supplier.is_deleted.is_(False))
            .order_by(Supplier.name.asc())
        )
        suppliers = list(result.scalars().all())

    data = report_svc.generate_supplier_report(suppliers)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=suppliers_report.xlsx"},
    )


@router.get("/categories", summary="Export category report as Excel", response_class=Response)
async def export_category_report(
    active_only: bool = Query(default=False),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: ReportService = Depends(_report_svc),
) -> Response:
    from sqlalchemy import and_, select
    from app.models.master_data import Category

    query = select(Category).where(Category.is_deleted.is_(False))
    if active_only:
        query = query.where(Category.is_active.is_(True))
    result = await db.execute(query.order_by(Category.name.asc()))
    categories = list(result.scalars().all())

    data = report_svc.generate_category_report(categories)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=categories_report.xlsx"},
    )
