"""
Stock Release report endpoints — Phase 5.

GET /api/v1/stock-release-reports/releases         — Excel stock release report
GET /api/v1/stock-release-reports/consumption      — Excel product consumption report
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.database.engine import get_db
from app.models.user import User
from app.services.stock_release import StockReleaseService
from app.services.stock_release_report import StockReleaseReportService

router = APIRouter()

_EXCEL_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _report_svc() -> StockReleaseReportService:
    return StockReleaseReportService()


@router.get(
    "/releases",
    summary="Export stock release report as Excel",
    response_class=Response,
)
async def export_stock_release_report(
    status: str | None = Query(default=None),
    purpose: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: StockReleaseReportService = Depends(_report_svc),
) -> Response:
    svc = StockReleaseService(db)
    releases = await svc.get_for_report(
        status=status,
        purpose=purpose,
        from_date=from_date,
        to_date=to_date,
    )
    data = report_svc.generate_stock_release_report(releases)
    return Response(
        content=data,
        media_type=_EXCEL_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename=stock_release_report.xlsx"
        },
    )


@router.get(
    "/consumption",
    summary="Export product consumption report as Excel",
    response_class=Response,
)
async def export_product_consumption_report(
    product_id: uuid.UUID | None = Query(default=None),
    purpose: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: StockReleaseReportService = Depends(_report_svc),
) -> Response:
    svc = StockReleaseService(db)
    # For consumption, always report on APPROVED releases only
    releases = await svc.get_for_report(
        status="APPROVED",
        purpose=purpose,
        from_date=from_date,
        to_date=to_date,
    )
    # Filter by product if specified
    if product_id is not None:
        filtered = []
        for sr in releases:
            matching_items = [i for i in sr.items if i.product_id == product_id]
            if matching_items:
                # Create a shallow copy with only matching items for report
                import copy
                sr_copy = copy.copy(sr)
                sr_copy.items = matching_items  # type: ignore[assignment]
                filtered.append(sr_copy)
        releases = filtered

    data = report_svc.generate_product_consumption_report(releases)
    return Response(
        content=data,
        media_type=_EXCEL_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename=product_consumption_report.xlsx"
        },
    )
