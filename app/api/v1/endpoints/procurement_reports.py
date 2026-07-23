"""
Procurement reports and dashboard endpoints — Phase 3.

GET /api/v1/procurement/reports/purchase-orders    -- Excel PO report
GET /api/v1/procurement/reports/grns               -- Excel GRN report
GET /api/v1/procurement/reports/supplier-purchases -- Excel supplier purchase report
GET /api/v1/procurement/dashboard                  -- procurement summary dashboard
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
from app.schemas.base import SuccessResponse
from app.schemas.procurement import ProcurementDashboard
from app.services.procurement import (
    GRNService,
    ProcurementDashboardService,
    PurchaseOrderService,
)
from app.services.procurement_report import ProcurementReportService

router = APIRouter()


def _report_svc() -> ProcurementReportService:
    return ProcurementReportService()


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@router.get(
    "/reports/purchase-orders",
    summary="Export Purchase Order report as Excel",
    response_class=Response,
)
async def export_po_report(
    supplier_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: ProcurementReportService = Depends(_report_svc),
) -> Response:
    svc = PurchaseOrderService(db)
    pos = await svc.get_for_report(
        supplier_id=supplier_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
    )
    data = report_svc.generate_po_report(pos)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=purchase_orders_report.xlsx"
        },
    )


@router.get(
    "/reports/grns",
    summary="Export GRN report as Excel",
    response_class=Response,
)
async def export_grn_report(
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    status: str | None = Query(default=None),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: ProcurementReportService = Depends(_report_svc),
) -> Response:
    svc = GRNService(db)
    grns = await svc.get_for_report(
        from_date=from_date,
        to_date=to_date,
        status=status,
    )
    data = report_svc.generate_grn_report(grns)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=grn_report.xlsx"},
    )


@router.get(
    "/reports/supplier-purchases",
    summary="Export Supplier Purchase report as Excel",
    response_class=Response,
)
async def export_supplier_purchase_report(
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    supplier_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_permission("reports:export")),
    db: AsyncSession = Depends(get_db),
    report_svc: ProcurementReportService = Depends(_report_svc),
) -> Response:
    svc = PurchaseOrderService(db)
    pos = await svc.get_for_report(
        supplier_id=supplier_id,
        from_date=from_date,
        to_date=to_date,
    )
    data = report_svc.generate_supplier_purchase_report(pos)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=supplier_purchases_report.xlsx"
        },
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get(
    "/dashboard",
    response_model=SuccessResponse[ProcurementDashboard],
    summary="Procurement dashboard summary",
)
async def get_procurement_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[ProcurementDashboard]:
    svc = ProcurementDashboardService(db)
    summary = await svc.get_summary()
    return SuccessResponse(data=ProcurementDashboard(**summary))
