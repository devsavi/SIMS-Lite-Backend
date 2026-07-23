"""
User, Role, Permission, and RefreshToken ORM models.

These models form the identity core of SIMS Lite. All tables use UUID
primary keys and include TimestampMixin columns for auditing.

Table relationships
-------------------
- users ←→ roles (many-to-many via user_roles association table)
- roles ←→ permissions (many-to-many via role_permissions association table)
- users → refresh_tokens (one-to-many)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Table,
    Column,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Association tables (pure join tables, no extra columns)
# ---------------------------------------------------------------------------

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# ---------------------------------------------------------------------------
# Permission model
# ---------------------------------------------------------------------------


class Permission(Base, UUIDMixin, TimestampMixin):
    """
    A granular action that can be permitted or denied.

    Permissions follow a ``resource:action`` naming convention, e.g.
    ``users:read``, ``inventory:write``, ``reports:export``.
    """

    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Relationships
    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
    )

    __table_args__ = (UniqueConstraint("resource", "action", name="uq_resource_action"),)

    def __repr__(self) -> str:
        return f"<Permission {self.name}>"


# ---------------------------------------------------------------------------
# Role model
# ---------------------------------------------------------------------------


class Role(Base, UUIDMixin, TimestampMixin):
    """
    A named collection of permissions assigned to users.

    Built-in roles: ADMIN, OFFICER, STORE_KEEPER.
    Roles can be customised or extended by administrators.
    """

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # system roles cannot be deleted

    # Relationships
    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
    )
    users: Mapped[list[User]] = relationship(
        "User",
        secondary=user_roles,
        back_populates="roles",
    )

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


class User(Base, UUIDMixin, TimestampMixin):
    """
    Core identity record for the SIMS application.

    Stores credentials, profile, and status information.
    Roles are assigned via the user_roles association table.
    """

    __tablename__ = "users"

    # Authentication fields
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Profile fields
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Status fields
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Account management
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_login_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Password reset
    password_reset_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    password_reset_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Email verification
    email_verification_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Relationships
    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",  # always load roles with the user
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def role_names(self) -> list[str]:
        return [r.name for r in self.roles]

    @property
    def all_permissions(self) -> set[str]:
        """Return the flat set of permission names granted by all roles."""
        perms: set[str] = set()
        for role in self.roles:
            for perm in role.permissions:
                perms.add(perm.name)
        return perms

    def has_permission(self, permission: str) -> bool:
        return self.is_superuser or permission in self.all_permissions

    def has_role(self, role_name: str) -> bool:
        return role_name in self.role_names

    def __repr__(self) -> str:
        return f"<User {self.email}>"


# ---------------------------------------------------------------------------
# RefreshToken model
# ---------------------------------------------------------------------------


class RefreshToken(Base, UUIDMixin, TimestampMixin):
    """
    Persisted refresh tokens for rotation and revocation.

    Each refresh token is a hashed reference.  On use, the old token
    is marked revoked and a new one is issued (token rotation).
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")

    @property
    def is_valid(self) -> bool:
        from datetime import UTC

        return not self.is_revoked and datetime.now(UTC) < self.expires_at

    def __repr__(self) -> str:
        return f"<RefreshToken user={self.user_id} revoked={self.is_revoked}>"
