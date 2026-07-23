"""
User, Role, and Permission Pydantic schemas.

Input schemas (Create/Update) validate incoming request data.
Output schemas (Read) control what fields are exposed in responses.
Never expose password_hash or internal tokens in Read schemas.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import AppBaseModel


# ---------------------------------------------------------------------------
# Permission schemas
# ---------------------------------------------------------------------------


class PermissionRead(AppBaseModel):
    """Public view of a permission record."""

    id: uuid.UUID
    name: str
    description: str | None
    resource: str
    action: str
    created_at: datetime


class PermissionCreate(AppBaseModel):
    """Payload to create a new permission."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    resource: str = Field(min_length=1, max_length=50)
    action: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def name_format(cls, v: str) -> str:
        """Enforce resource:action format."""
        if ":" not in v:
            raise ValueError("Permission name must follow 'resource:action' format.")
        return v.lower()


# ---------------------------------------------------------------------------
# Role schemas
# ---------------------------------------------------------------------------


class RoleRead(AppBaseModel):
    """Public view of a role (with its permissions)."""

    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    permissions: list[PermissionRead] = []
    created_at: datetime


class RoleReadSummary(AppBaseModel):
    """Lightweight role view (without permissions list)."""

    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool


class RoleCreate(AppBaseModel):
    """Payload to create a role."""

    name: str = Field(min_length=1, max_length=50)
    description: str | None = None
    permission_ids: list[uuid.UUID] = Field(default_factory=list)


class RoleUpdate(AppBaseModel):
    """Partial update for a role."""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = None
    permission_ids: list[uuid.UUID] | None = None


class RoleAssignRequest(AppBaseModel):
    """Assign one or more roles to a user."""

    role_ids: list[uuid.UUID] = Field(min_length=1)


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------


class UserRead(AppBaseModel):
    """
    Safe public representation of a User.

    Never includes password_hash or reset/verification tokens.
    """

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    full_name: str
    phone: str | None
    is_active: bool
    is_verified: bool
    is_superuser: bool
    last_login: datetime | None
    roles: list[RoleReadSummary] = []
    created_at: datetime
    updated_at: datetime


class UserReadBrief(AppBaseModel):
    """Minimal user summary for embedded references."""

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool


class UserCreate(AppBaseModel):
    """
    Admin-level user creation payload.

    Used by admins to create users directly (no email verification needed
    in admin-created accounts unless enforced by policy).
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool = True
    is_verified: bool = False
    role_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        errors: list[str] = []
        if not any(c.isupper() for c in v):
            errors.append("at least one uppercase letter")
        if not any(c.islower() for c in v):
            errors.append("at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            errors.append("at least one digit")
        if not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in v):
            errors.append("at least one special character")
        if errors:
            raise ValueError(
                f"Password must contain: {', '.join(errors)}."
            )
        return v


class UserUpdate(AppBaseModel):
    """Partial update payload for user profile fields."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)


class UserAdminUpdate(AppBaseModel):
    """Admin-level user update (allows toggling status flags)."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    is_verified: bool | None = None


# ---------------------------------------------------------------------------
# Audit log schemas
# ---------------------------------------------------------------------------


class AuditLogRead(AppBaseModel):
    """Public view of an audit log entry."""

    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    status: str
    detail: dict | None
    created_at: datetime
