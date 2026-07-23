"""
Role and Permission management service.

Handles creation, update, and deletion of roles and permissions.
System roles (ADMIN, OFFICER, STORE_KEEPER) cannot be deleted.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.models.user import Permission, Role, User
from app.repositories.audit_log import AuditLogRepository
from app.repositories.user import PermissionRepository, RoleRepository
from app.schemas.user import PermissionCreate, RoleCreate, RoleUpdate

logger = get_logger(__name__)


class RoleService:
    """Business logic for roles and permissions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._roles = RoleRepository(session)
        self._permissions = PermissionRepository(session)
        self._audit = AuditLogRepository(session)

    # ------------------------------------------------------------------
    # Permission CRUD
    # ------------------------------------------------------------------

    async def create_permission(
        self,
        payload: PermissionCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Permission:
        name = payload.name.lower()
        if await self._permissions.name_exists(name):
            raise ConflictError(f"Permission '{name}' already exists.")

        perm = await self._permissions.create(
            name=name,
            description=payload.description,
            resource=payload.resource.lower(),
            action=payload.action.lower(),
        )
        await self._audit.log(
            action="permission.create",
            actor_id=actor.id,
            resource_type="Permission",
            resource_id=str(perm.id),
            ip_address=ip_address,
            detail={"name": name},
        )
        return perm

    async def get_permission(self, perm_id: uuid.UUID) -> Permission:
        perm = await self._permissions.get_by_id(perm_id)
        if perm is None:
            raise NotFoundError(f"Permission {perm_id} not found.")
        return perm

    async def list_permissions(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Permission]:
        return await self._permissions.get_all(offset=offset, limit=limit)

    async def delete_permission(
        self,
        perm_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        perm = await self.get_permission(perm_id)
        await self._audit.log(
            action="permission.delete",
            actor_id=actor.id,
            resource_type="Permission",
            resource_id=str(perm_id),
            ip_address=ip_address,
            detail={"name": perm.name},
        )
        await self._permissions.delete(perm)

    # ------------------------------------------------------------------
    # Role CRUD
    # ------------------------------------------------------------------

    async def create_role(
        self,
        payload: RoleCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Role:
        name = payload.name.upper()
        existing = await self._roles.get_by_name(name)
        if existing:
            raise ConflictError(f"Role '{name}' already exists.")

        permissions = (
            await self._permissions.get_by_ids(payload.permission_ids)
            if payload.permission_ids
            else []
        )

        role = await self._roles.create(
            name=name,
            description=payload.description,
            is_system=False,
        )
        if permissions:
            role.permissions.extend(permissions)
            self._session.add(role)
            await self._session.flush()
            await self._session.refresh(role)

        await self._audit.log(
            action="role.create",
            actor_id=actor.id,
            resource_type="Role",
            resource_id=str(role.id),
            ip_address=ip_address,
            detail={"name": name},
        )
        return role

    async def get_role(self, role_id: uuid.UUID) -> Role:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await self._session.execute(
            select(Role)
            .where(Role.id == role_id)
            .options(selectinload(Role.permissions))
        )
        role = result.scalar_one_or_none()
        if role is None:
            raise NotFoundError(f"Role {role_id} not found.")
        return role

    async def list_roles(self) -> list[Role]:
        return await self._roles.get_all_with_permissions()

    async def update_role(
        self,
        role_id: uuid.UUID,
        payload: RoleUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Role:
        role = await self.get_role(role_id)
        changes: dict = {}

        if payload.name is not None:
            changes["name"] = payload.name.upper()
        if payload.description is not None:
            changes["description"] = payload.description

        if changes:
            role = await self._roles.update(role, **changes)

        if payload.permission_ids is not None:
            perms = await self._permissions.get_by_ids(payload.permission_ids)
            role.permissions = perms  # type: ignore[assignment]
            self._session.add(role)
            await self._session.flush()
            await self._session.refresh(role)

        await self._audit.log(
            action="role.update",
            actor_id=actor.id,
            resource_type="Role",
            resource_id=str(role_id),
            ip_address=ip_address,
            detail=changes,
        )
        return role

    async def delete_role(
        self,
        role_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        role = await self.get_role(role_id)
        if role.is_system:
            raise ForbiddenError(f"System role '{role.name}' cannot be deleted.")

        await self._audit.log(
            action="role.delete",
            actor_id=actor.id,
            resource_type="Role",
            resource_id=str(role_id),
            ip_address=ip_address,
            detail={"name": role.name},
        )
        await self._roles.delete(role)
