"""
User, Role, Permission, and RefreshToken repositories.

Domain-specific database queries built on top of BaseRepository.
All methods are async and use the project's AsyncSession pattern.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.base import Base
from app.models.user import Permission, RefreshToken, Role, User
from app.repositories.base import BaseRepository


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------


class UserRepository(BaseRepository[User]):
    """Queries for the ``users`` table."""

    model = User

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email address (case-insensitive)."""
        result = await self.session.execute(
            select(User)
            .where(User.email == email.lower().strip())
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_roles(self, user_id: uuid.UUID) -> User | None:
        """Fetch a user with roles and permissions eagerly loaded."""
        result = await self.session.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def get_by_reset_token(self, token: str) -> User | None:
        """Find a user whose password_reset_token matches."""
        result = await self.session.execute(
            select(User).where(User.password_reset_token == token)
        )
        return result.scalar_one_or_none()

    async def get_by_verification_token(self, token: str) -> User | None:
        """Find a user whose email_verification_token matches."""
        result = await self.session.execute(
            select(User).where(User.email_verification_token == token)
        )
        return result.scalar_one_or_none()

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        active_only: bool = False,
    ) -> tuple[list[User], int]:
        """Return (users, total_count) with optional active filter."""
        from sqlalchemy import func

        query = select(User).options(selectinload(User.roles))

        if active_only:
            query = query.where(User.is_active.is_(True))

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        users_result = await self.session.execute(
            query.order_by(User.created_at.desc()).offset(offset).limit(limit)
        )
        return list(users_result.scalars().all()), total

    async def email_exists(self, email: str) -> bool:
        """Return True if an account with this email already exists."""
        from sqlalchemy import exists

        result = await self.session.execute(
            select(exists().where(User.email == email.lower().strip()))
        )
        return bool(result.scalar())

    async def increment_failed_logins(self, user: User) -> User:
        """Atomically increment the failed login counter."""
        user.failed_login_attempts += 1
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def reset_failed_logins(self, user: User) -> User:
        """Reset the failed login counter and clear any lock."""
        user.failed_login_attempts = 0
        user.locked_until = None
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user


# ---------------------------------------------------------------------------
# RefreshTokenRepository
# ---------------------------------------------------------------------------


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Queries for the ``refresh_tokens`` table."""

    model = RefreshToken

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Look up a token by its hashed value."""
        result = await self.session.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .options(selectinload(RefreshToken.user))
        )
        return result.scalar_one_or_none()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke all active tokens for a user (logout all devices)."""
        from sqlalchemy import update

        result = await self.session.execute(
            update(RefreshToken)
            .where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked.is_(False),
                )
            )
            .values(is_revoked=True)
        )
        await self.session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def delete_expired(self, user_id: uuid.UUID) -> int:
        """Clean up expired tokens for a given user."""
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(RefreshToken).where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.expires_at < datetime.now(UTC),
                )
            )
        )
        await self.session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def count_active_for_user(self, user_id: uuid.UUID) -> int:
        """Count non-revoked, non-expired tokens for a user."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count()).where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked.is_(False),
                    RefreshToken.expires_at > datetime.now(UTC),
                )
            )
        )
        return result.scalar_one()


# ---------------------------------------------------------------------------
# RoleRepository
# ---------------------------------------------------------------------------


class RoleRepository(BaseRepository[Role]):
    """Queries for the ``roles`` table."""

    model = Role

    async def get_by_name(self, name: str) -> Role | None:
        result = await self.session.execute(
            select(Role)
            .where(Role.name == name.upper())
            .options(selectinload(Role.permissions))
        )
        return result.scalar_one_or_none()

    async def get_by_ids(self, ids: list[uuid.UUID]) -> list[Role]:
        if not ids:
            return []
        result = await self.session.execute(
            select(Role).where(Role.id.in_(ids))
        )
        return list(result.scalars().all())

    async def get_all_with_permissions(self) -> list[Role]:
        result = await self.session.execute(
            select(Role).options(selectinload(Role.permissions))
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# PermissionRepository
# ---------------------------------------------------------------------------


class PermissionRepository(BaseRepository[Permission]):
    """Queries for the ``permissions`` table."""

    model = Permission

    async def get_by_name(self, name: str) -> Permission | None:
        result = await self.session.execute(
            select(Permission).where(Permission.name == name.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_ids(self, ids: list[uuid.UUID]) -> list[Permission]:
        if not ids:
            return []
        result = await self.session.execute(
            select(Permission).where(Permission.id.in_(ids))
        )
        return list(result.scalars().all())

    async def name_exists(self, name: str) -> bool:
        from sqlalchemy import exists

        result = await self.session.execute(
            select(exists().where(Permission.name == name.lower()))
        )
        return bool(result.scalar())
