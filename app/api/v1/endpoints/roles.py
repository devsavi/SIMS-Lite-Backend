"""
Role management endpoints (admin only).

GET    /api/v1/roles/          — List all roles
POST   /api/v1/roles/          — Create a role
GET    /api/v1/roles/{id}      — Get a specific role
PUT    /api/v1/roles/{id}      — Update a role
DELETE /api/v1/roles/{id}      — Delete a role (non-system only)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, require_roles
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import SuccessResponse
from app.schemas.user import RoleCreate, RoleRead, RoleUpdate
from app.services.role import RoleService

router = APIRouter()


def _role_service(db: AsyncSession = Depends(get_db)) -> RoleService:
    return RoleService(db)


@router.get(
    "/",
    response_model=SuccessResponse[list[RoleRead]],
    summary="List all roles",
)
async def list_roles(
    current_user: User = Depends(require_roles("ADMIN")),
    svc: RoleService = Depends(_role_service),
) -> SuccessResponse[list[RoleRead]]:
    roles = await svc.list_roles()
    return SuccessResponse(data=[RoleRead.model_validate(r) for r in roles])


@router.post(
    "/",
    response_model=SuccessResponse[RoleRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new role (admin only)",
)
async def create_role(
    payload: RoleCreate,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: RoleService = Depends(_role_service),
) -> SuccessResponse[RoleRead]:
    ip = get_client_ip(request)
    role = await svc.create_role(payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=RoleRead.model_validate(role))


@router.get(
    "/{role_id}",
    response_model=SuccessResponse[RoleRead],
    summary="Get role by ID",
)
async def get_role(
    role_id: uuid.UUID,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: RoleService = Depends(_role_service),
) -> SuccessResponse[RoleRead]:
    role = await svc.get_role(role_id)
    return SuccessResponse(data=RoleRead.model_validate(role))


@router.put(
    "/{role_id}",
    response_model=SuccessResponse[RoleRead],
    summary="Update a role (admin only)",
)
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: RoleService = Depends(_role_service),
) -> SuccessResponse[RoleRead]:
    ip = get_client_ip(request)
    role = await svc.update_role(role_id, payload, actor=current_user, ip_address=ip)
    return SuccessResponse(data=RoleRead.model_validate(role))


@router.delete(
    "/{role_id}",
    response_model=SuccessResponse[dict],
    summary="Delete a role (admin only, non-system roles)",
)
async def delete_role(
    role_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_roles("ADMIN")),
    svc: RoleService = Depends(_role_service),
) -> SuccessResponse[dict]:
    ip = get_client_ip(request)
    await svc.delete_role(role_id, actor=current_user, ip_address=ip)
    return SuccessResponse(data={"deleted": True, "id": str(role_id)})
