"""
Permission management endpoints (admin only).

GET    /api/v1/permissions/       — List all permissions
POST   /api/v1/permissions/       — Create a permission
GET    /api/v1/permissions/{id}   — Get a specific permission
DELETE /api/v1/permissions/{id}   — Delete a permission
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, require_roles
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import SuccessResponse
from app.schemas.user import PermissionCreate, PermissionRead
from app.services.role import RoleService

router = APIRouter()


def _role_service(db: AsyncSession = Depends(get_db)) -> RoleService:
    return RoleService(db)


@router.get(
    "/",
    response_model=SuccessResponse[list[PermissionRead]],
    summary="List all permissions",
)
async def list_permissions(
    current_user: User = Depends(require_roles("ADMIN")),
    svc: RoleService = Depends(_role_service),
) -> SuccessResponse[list[PermissionRead]]:
    perms = await svc.list_permissions()
    return SuccessResponse(data=[PermissionRead.model_validate(p) for p in perms])


@router.post(
    "/",
    response_model=SuccessResponse[PermissionRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new permission (admin only)",
)
async def create_permission(
    payload: PermissionCreate,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: RoleService = Depends(_role_service),
) -> SuccessResponse[PermissionRead]:
    ip = get_client_ip(request)
    perm = await svc.create_permission(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=PermissionRead.model_validate(perm))


@router.get(
    "/{permission_id}",
    response_model=SuccessResponse[PermissionRead],
    summary="Get permission by ID",
)
async def get_permission(
    permission_id: uuid.UUID,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: RoleService = Depends(_role_service),
) -> SuccessResponse[PermissionRead]:
    perm = await svc.get_permission(permission_id)
    return SuccessResponse(data=PermissionRead.model_validate(perm))


@router.delete(
    "/{permission_id}",
    response_model=SuccessResponse[dict],
    summary="Delete a permission (admin only)",
)
async def delete_permission(
    permission_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: RoleService = Depends(_role_service),
) -> SuccessResponse[dict]:
    ip = get_client_ip(request)
    await svc.delete_permission(permission_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data={"deleted": True, "id": str(permission_id)})
