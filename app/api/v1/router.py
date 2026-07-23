"""
API v1 root router.

All feature routers are registered here.  Import and include this
router in main.py once, keeping main.py clean.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health, system, websocket

# Phase 1 — Authentication & User Management
from app.api.v1.endpoints import auth, permissions, profile, roles, users

# Phase 2 — Master Data Management
from app.api.v1.endpoints import brands, categories, products, reports, suppliers, uoms

# Phase 3 — Procurement
from app.api.v1.endpoints import grns, inventory, procurement_reports, purchase_orders

# Phase 4 — Inventory Engine
from app.api.v1.endpoints import (
    inventory_dashboard,
    inventory_ledger,
    inventory_reports,
    stock_adjustments,
)

api_router = APIRouter()

# ---------------------------------------------------------------------------
# Core infrastructure endpoints
# ---------------------------------------------------------------------------
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])

# ---------------------------------------------------------------------------
# Phase 1 — Authentication & User Management
# ---------------------------------------------------------------------------
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(profile.router, prefix="/profile", tags=["Profile"])
api_router.include_router(roles.router, prefix="/roles", tags=["Roles"])
api_router.include_router(
    permissions.router, prefix="/permissions", tags=["Permissions"]
)

# ---------------------------------------------------------------------------
# Phase 2 — Master Data Management
# ---------------------------------------------------------------------------
api_router.include_router(
    categories.router, prefix="/categories", tags=["Categories"]
)
api_router.include_router(brands.router, prefix="/brands", tags=["Brands"])
api_router.include_router(uoms.router, prefix="/uoms", tags=["Units of Measure"])
api_router.include_router(suppliers.router, prefix="/suppliers", tags=["Suppliers"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])

# ---------------------------------------------------------------------------
# Phase 3 — Procurement
# ---------------------------------------------------------------------------
api_router.include_router(
    purchase_orders.router,
    prefix="/purchase-orders",
    tags=["Purchase Orders"],
)
api_router.include_router(grns.router, prefix="/grns", tags=["GRNs"])
api_router.include_router(
    procurement_reports.router,
    prefix="/procurement",
    tags=["Procurement Reports & Dashboard"],
)

# ---------------------------------------------------------------------------
# Phase 4 — Inventory Engine
# ---------------------------------------------------------------------------
api_router.include_router(
    inventory.router,
    prefix="/inventory",
    tags=["Inventory"],
)
api_router.include_router(
    stock_adjustments.router,
    prefix="/stock-adjustments",
    tags=["Stock Adjustments"],
)
api_router.include_router(
    inventory_ledger.router,
    prefix="/inventory-ledger",
    tags=["Inventory Ledger"],
)
api_router.include_router(
    inventory_dashboard.router,
    prefix="/dashboard",
    tags=["Dashboard"],
)
api_router.include_router(
    inventory_reports.router,
    prefix="/inventory-reports",
    tags=["Inventory Reports"],
)
