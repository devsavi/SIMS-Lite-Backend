"""
API v1 root router.

All feature routers are registered here.  Import and include this
router in main.py once, keeping main.py clean.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health, system, websocket

api_router = APIRouter()

# Core infrastructure endpoints
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])

# Future feature routers will be registered here in later phases:
# api_router.include_router(users.router, prefix="/users", tags=["Users"])
