"""
Inventory report endpoints — Phase 4.

GET /api/v1/inventory-reports/current-stock     — Excel current stock report
GET /api/v1/inventory-reports/ledger            — Excel inventory ledger report
GET /api/v1/inventory-reports/adjustments       — Excel stock adjustment report
GET /api/v1/inventory-reports/low-stock         — Excel low stock report
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_permission
from app.database.engine import get_db
from app.models.user import User
from app.services.inventory import InventoryLedgerService, InventoryService, StockAdjustmentService
from app.services.inventory_report import InventoryReportService

router = APIRouter()

_EXCEL_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _report_svc() -> InventoryReportService:
    return InventoryReportService()


@router.get(
    "/current-stock",
    summary="Export current stock report as Excel",
    response_class=Response,
)
async def export_current_stock_report(
    category_id: uuid.UUID | None = Query(default=None),
    supplier_id: uuid.UUID | None = Query(default=None),
    low_stock_only: bool = Query(default=False),
    out_of_stock_only: bool = Query(default=False),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: InventoryReportService = Depends(_report_svc),
) -> Response:
    svc = InventoryService(db)
    items = await svc._inv.get_all_for_report(
        category_id=category_id,
        supplier_id=supplier_id,
        low_stock_only=low_stock_only,
        out_of_stock_only=out_of_stock_only,
    )
    data = report_svc.generate_current_stock_report(items)
    return Response(
        content=data,
        media_type=_EXCEL_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename=current_stock_report.xlsx"
        },
    )


@router.get(
    "/ledger",
    summary="Export inventory ledger report as Excel",
    response_class=Response,
)
async def export_ledger_report(
    product_id: uuid.UUID | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    reference_type: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: InventoryReportService = Depends(_report_svc),
) -> Response:
    svc = InventoryLedgerService(db)
    entries = await svc.get_all_for_report(
        product_id=product_id,
        entry_type=entry_type,
        reference_type=reference_type,
        from_date=from_date,
        to_date=to_date,
    )
    data = report_svc.generate_inventory_ledger_report(entries)
    return Response(
        content=data,
        media_type=_EXCEL_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename=inventory_ledger_report.xlsx"
        },
    )


@router.get(
    "/adjustments",
    summary="Export stock adjustment report as Excel",
    response_class=Response,
)
async def export_adjustment_report(
    status: str | None = Query(default=None),
    adjustment_type: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: InventoryReportService = Depends(_report_svc),
) -> Response:
    svc = StockAdjustmentService(db)
    adjustments = await svc.get_for_report(
        status=status,
        adjustment_type=adjustment_type,
        from_date=from_date,
        to_date=to_date,
    )
    data = report_svc.generate_stock_adjustment_report(adjustments)
    return Response(
        content=data,
        media_type=_EXCEL_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename=stock_adjustment_report.xlsx"
        },
    )


@router.get(
    "/low-stock",
    summary="Export low stock report as Excel",
    response_class=Response,
)
async def export_low_stock_report(
    category_id: uuid.UUID | None = Query(default=None),
    supplier_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: InventoryReportService = Depends(_report_svc),
) -> Response:
    svc = InventoryService(db)
    # Low stock = qty > 0 and qty <= reorder_level, PLUS out of stock items
    low_items = await svc._inv.get_all_for_report(
        category_id=category_id,
        supplier_id=supplier_id,
        low_stock_only=True,
    )
    out_items = await svc._inv.get_all_for_report(
        category_id=category_id,
        supplier_id=supplier_id,
        out_of_stock_only=True,
    )
    # Merge: out of stock first, then low stock
    all_items = out_items + low_items
    data = report_svc.generate_low_stock_report(all_items)
    return Response(
        content=data,
        media_type=_EXCEL_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename=low_stock_report.xlsx"
        },
    )
