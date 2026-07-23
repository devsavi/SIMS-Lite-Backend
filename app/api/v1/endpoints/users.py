"""
User management endpoints (admin-level).

GET    /api/v1/users/           — List all users (paginated)
POST   /api/v1/users/           — Create a user
GET    /api/v1/users/{id}       — Get a specific user
PUT    /api/v1/users/{id}       — Update a user
DELETE /api/v1/users/{id}       — Delete a user
POST   /api/v1/users/{id}/activate    — Activate a deactivated user
POST   /api/v1/users/{id}/deactivate  — Deactivate a user
PUT    /api/v1/users/{id}/roles       — Assign roles to a user
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, get_current_user, require_roles
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.user import (
    RoleAssignRequest,
    UserAdminUpdate,
    UserCreate,
    UserRead,
)
from app.services.user import UserService

router = APIRouter()


def _user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


# ---------------------------------------------------------------------------
# List users
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedResponse[UserRead],
    summary="List all users (admin only)",
)
async def list_users(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    active_only: bool = Query(default=False),
    current_user: User = Depends(require_roles("ADMIN")),
    svc: UserService = Depends(_user_service),
) -> PaginatedResponse[UserRead]:
    offset = (page - 1) * size
    users, total = await svc.list_users(
        offset=offset, limit=size, active_only=active_only
    )
    pages = (total + size - 1) // size
    return PaginatedResponse(
        data=[UserRead.model_validate(u) for u in users],
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


# ---------------------------------------------------------------------------
# Create user
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=SuccessResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
)
async def create_user(
    payload: UserCreate,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: UserService = Depends(_user_service),
) -> SuccessResponse[UserRead]:
    ip = get_client_ip(request)
    user = await svc.create_user(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=UserRead.model_validate(user))


# ---------------------------------------------------------------------------
# Get / Update / Delete single user
# ---------------------------------------------------------------------------


@router.get(
    "/{user_id}",
    response_model=SuccessResponse[UserRead],
    summary="Get user by ID",
)
async def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_roles("ADMIN", "OFFICER")),
    svc: UserService = Depends(_user_service),
) -> SuccessResponse[UserRead]:
    user = await svc.get_user(user_id)
    return SuccessResponse(data=UserRead.model_validate(user))


@router.put(
    "/{user_id}",
    response_model=SuccessResponse[UserRead],
    summary="Update user (admin only)",
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserAdminUpdate,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: UserService = Depends(_user_service),
) -> SuccessResponse[UserRead]:
    ip = get_client_ip(request)
    user = await svc.update_user(user_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=UserRead.model_validate(user))


@router.delete(
    "/{user_id}",
    response_model=SuccessResponse[dict],
    summary="Permanently delete a user (superuser only)",
)
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: UserService = Depends(_user_service),
) -> SuccessResponse[dict]:
    from app.core.deps import require_superuser

    if not current_user.is_superuser:
        from app.core.exceptions import ForbiddenError

        raise ForbiddenError("Only superusers can permanently delete users.")

    ip = get_client_ip(request)
    await svc.delete_user(user_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data={"deleted": True, "id": str(user_id)})


# ---------------------------------------------------------------------------
# Activate / Deactivate
# ---------------------------------------------------------------------------


@router.post(
    "/{user_id}/activate",
    response_model=SuccessResponse[UserRead],
    summary="Activate a user account (admin only)",
)
async def activate_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: UserService = Depends(_user_service),
) -> SuccessResponse[UserRead]:
    ip = get_client_ip(request)
    user = await svc.activate_user(user_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=UserRead.model_validate(user))


@router.post(
    "/{user_id}/deactivate",
    response_model=SuccessResponse[UserRead],
    summary="Deactivate a user account (admin only)",
)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: UserService = Depends(_user_service),
) -> SuccessResponse[UserRead]:
    ip = get_client_ip(request)
    user = await svc.deactivate_user(user_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data=UserRead.model_validate(user))


# ---------------------------------------------------------------------------
# Role assignment
# ---------------------------------------------------------------------------


@router.put(
    "/{user_id}/roles",
    response_model=SuccessResponse[UserRead],
    summary="Assign roles to a user (admin only)",
)
async def assign_roles(
    user_id: uuid.UUID,
    payload: RoleAssignRequest,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: UserService = Depends(_user_service),
) -> SuccessResponse[UserRead]:
    ip = get_client_ip(request)
    user = await svc.assign_roles(
        user_id, payload.role_ids, actor=current_user, ip_address=ip
    )
    return SuccessResponse(data=UserRead.model_validate(user))
