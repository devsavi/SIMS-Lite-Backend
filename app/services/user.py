"""
User management service.

Handles admin-level operations:
- Create/read/update/deactivate users
- Role assignment / revocation
- Profile management
- User listing with pagination
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.user import User
from app.repositories.audit_log import AuditLogRepository
from app.repositories.user import RoleRepository, UserRepository
from app.schemas.user import (
    UserAdminUpdate,
    UserCreate,
    UserRead,
    UserUpdate,
)

logger = get_logger(__name__)


class UserService:
    """Business logic for user CRUD and profile management."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._roles = RoleRepository(session)
        self._audit = AuditLogRepository(session)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_user(
        self,
        payload: UserCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        """
        Admin-level user creation.

        Raises ConflictError if the email is already registered.
        """
        email = payload.email.lower().strip()
        if await self._users.email_exists(email):
            raise ConflictError(f"An account with email '{email}' already exists.")

        # Resolve roles
        roles = await self._roles.get_by_ids(payload.role_ids) if payload.role_ids else []

        user = await self._users.create(
            email=email,
            password_hash=hash_password(payload.password),
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            phone=payload.phone,
            is_active=payload.is_active,
            is_verified=payload.is_verified,
        )

        if roles:
            user.roles.extend(roles)
            self._session.add(user)
            await self._session.flush()
            await self._session.refresh(user)

        await self._audit.log(
            action="user.create",
            actor_id=actor.id,
            resource_type="User",
            resource_id=str(user.id),
            ip_address=ip_address,
            detail={"email": email},
        )

        logger.info("User created by admin", created_id=str(user.id), actor_id=str(actor.id))
        return user

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_user(self, user_id: uuid.UUID) -> User:
        """Fetch a user by ID. Raises NotFoundError if missing."""
        user = await self._users.get_by_id_with_roles(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found.")
        return user

    async def list_users(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        active_only: bool = False,
    ) -> tuple[list[User], int]:
        """Return paginated users and total count."""
        return await self._users.get_all_paginated(
            offset=offset, limit=limit, active_only=active_only
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_user(
        self,
        user_id: uuid.UUID,
        payload: UserAdminUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        """Admin-level update of any user's fields."""
        user = await self.get_user(user_id)
        changes: dict = {}

        if payload.first_name is not None:
            changes["first_name"] = payload.first_name.strip()
        if payload.last_name is not None:
            changes["last_name"] = payload.last_name.strip()
        if payload.phone is not None:
            changes["phone"] = payload.phone
        if payload.is_active is not None:
            changes["is_active"] = payload.is_active
        if payload.is_verified is not None:
            changes["is_verified"] = payload.is_verified

        if changes:
            user = await self._users.update(user, **changes)

        await self._audit.log(
            action="user.update",
            actor_id=actor.id,
            resource_type="User",
            resource_id=str(user_id),
            ip_address=ip_address,
            detail=changes,
        )
        return user

    async def update_profile(
        self,
        user: User,
        payload: UserUpdate,
        *,
        ip_address: str | None = None,
    ) -> User:
        """Self-service profile update (name, phone)."""
        changes: dict = {}
        if payload.first_name is not None:
            changes["first_name"] = payload.first_name.strip()
        if payload.last_name is not None:
            changes["last_name"] = payload.last_name.strip()
        if payload.phone is not None:
            changes["phone"] = payload.phone

        if changes:
            user = await self._users.update(user, **changes)

        await self._audit.log(
            action="user.profile_update",
            actor_id=user.id,
            resource_type="User",
            resource_id=str(user.id),
            ip_address=ip_address,
            detail=changes,
        )
        return user

    # ------------------------------------------------------------------
    # Activate / Deactivate
    # ------------------------------------------------------------------

    async def activate_user(
        self,
        user_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        """Activate a deactivated user account."""
        user = await self.get_user(user_id)
        if user.id == actor.id:
            raise ForbiddenError("You cannot activate your own account via this endpoint.")
        user = await self._users.update(user, is_active=True)

        await self._audit.log(
            action="user.activate",
            actor_id=actor.id,
            resource_type="User",
            resource_id=str(user_id),
            ip_address=ip_address,
        )
        return user

    async def deactivate_user(
        self,
        user_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        """Deactivate an active user account."""
        user = await self.get_user(user_id)
        if user.id == actor.id:
            raise ForbiddenError("You cannot deactivate your own account.")
        if user.is_superuser:
            raise ForbiddenError("Superuser accounts cannot be deactivated.")

        user = await self._users.update(user, is_active=False)

        await self._audit.log(
            action="user.deactivate",
            actor_id=actor.id,
            resource_type="User",
            resource_id=str(user_id),
            ip_address=ip_address,
        )
        return user

    # ------------------------------------------------------------------
    # Role assignment
    # ------------------------------------------------------------------

    async def assign_roles(
        self,
        user_id: uuid.UUID,
        role_ids: list[uuid.UUID],
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> User:
        """Replace the user's role set with the provided role IDs."""
        user = await self.get_user(user_id)
        roles = await self._roles.get_by_ids(role_ids)

        user.roles = roles  # type: ignore[assignment]
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)

        await self._audit.log(
            action="user.roles_assign",
            actor_id=actor.id,
            resource_type="User",
            resource_id=str(user_id),
            ip_address=ip_address,
            detail={"role_ids": [str(r) for r in role_ids]},
        )
        return user

    # ------------------------------------------------------------------
    # Delete (hard delete — use deactivate for soft delete)
    # ------------------------------------------------------------------

    async def delete_user(
        self,
        user_id: uuid.UUID,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        """
        Permanently delete a user.

        Only superusers can call this. Use deactivate for standard ops.
        """
        user = await self.get_user(user_id)
        if user.id == actor.id:
            raise ForbiddenError("You cannot delete your own account.")
        if user.is_superuser:
            raise ForbiddenError("Superuser accounts cannot be deleted.")

        await self._audit.log(
            action="user.delete",
            actor_id=actor.id,
            resource_type="User",
            resource_id=str(user_id),
            ip_address=ip_address,
            detail={"email": user.email},
        )

        await self._users.delete(user)
        logger.info("User deleted", deleted_id=str(user_id), actor_id=str(actor.id))
