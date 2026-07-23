"""
Profile endpoints — authenticated user managing their own data.

GET  /api/v1/profile/   — Get own profile
PUT  /api/v1/profile/   — Update own profile (name, phone)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, get_current_user
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import SuccessResponse
from app.schemas.user import UserRead, UserUpdate
from app.services.user import UserService

router = APIRouter()


def _user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


@router.get(
    "/",
    response_model=SuccessResponse[UserRead],
    summary="Get the authenticated user's profile",
)
async def get_profile(
    current_user: User = Depends(get_current_user),
) -> SuccessResponse[UserRead]:
    """Return the full profile of the currently authenticated user."""
    return SuccessResponse(data=UserRead.model_validate(current_user))


@router.put(
    "/",
    response_model=SuccessResponse[UserRead],
    summary="Update the authenticated user's profile",
)
async def update_profile(
    payload: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: UserService = Depends(_user_service),
) -> SuccessResponse[UserRead]:
    """Update first name, last name, or phone for the current user."""
    ip = get_client_ip(request)
    updated = await svc.update_profile(current_user, payload, ip_address=ip)
    return SuccessResponse(data=UserRead.model_validate(updated))
