"""
Inventory Dashboard endpoints — Phase 4 + 5.

GET /api/v1/dashboard/inventory          — Inventory KPI dashboard (Phase 4)
GET /api/v1/dashboard/inventory/extended — Extended dashboard with stock release widgets (Phase 5)
GET /api/v1/dashboard/stock-releases     — Stock release KPIs (Phase 5)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import SuccessResponse
from app.schemas.inventory import InventoryDashboard
from app.schemas.stock_release import InventoryDashboardExtended, StockReleaseDashboard
from app.services.inventory import InventoryDashboardService
from app.services.stock_release import StockReleaseDashboardService

router = APIRouter()


@router.get(
    "/inventory",
    response_model=SuccessResponse[InventoryDashboard],
    summary="Inventory dashboard KPIs",
)
async def get_inventory_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[InventoryDashboard]:
    svc = InventoryDashboardService(db)
    data = await svc.get_summary()
    return SuccessResponse(data=InventoryDashboard(**data))


@router.get(
    "/stock-releases",
    response_model=SuccessResponse[StockReleaseDashboard],
    summary="Stock release KPI widgets (today's releases, monthly quantity, top products)",
)
async def get_stock_release_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[StockReleaseDashboard]:
    svc = StockReleaseDashboardService(db)
    data = await svc.get_summary()
    return SuccessResponse(data=StockReleaseDashboard(**data))


@router.get(
    "/inventory/extended",
    response_model=SuccessResponse[InventoryDashboardExtended],
    summary="Extended inventory dashboard — inventory KPIs + stock release widgets",
)
async def get_extended_inventory_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[InventoryDashboardExtended]:
    inv_svc = InventoryDashboardService(db)
    sr_svc = StockReleaseDashboardService(db)

    inv_data = await inv_svc.get_summary()
    sr_data = await sr_svc.get_summary()

    combined = {**inv_data, **sr_data}
    return SuccessResponse(data=InventoryDashboardExtended(**combined))
