"""
API v1 root router.

All feature routers are registered here.  Import and include this
router in main.py once, keeping main.py clean.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health, system, websocket

# Phase 1 — Authentication & User Management
from app.api.v1.endpoints import auth, permissions, profile, roles, users

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
