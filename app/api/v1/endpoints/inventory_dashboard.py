"""
Inventory Dashboard endpoint — Phase 4.

GET /api/v1/dashboard/inventory  — Inventory KPI dashboard
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import SuccessResponse
from app.schemas.inventory import InventoryDashboard
from app.services.inventory import InventoryDashboardService

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
