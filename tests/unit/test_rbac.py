"""
Unit tests for RBAC — roles, permissions, and the dependency helpers.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.deps import require_permission, require_roles
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.models.user import Permission, Role, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_with_roles(*role_names: str, is_superuser: bool = False) -> User:
    user = User()
    user.id = uuid.uuid4()
    user.email = "user@test.com"
    user.first_name = "Test"
    user.last_name = "User"
    user.is_active = True
    user.is_superuser = is_superuser

    roles = []
    for name in role_names:
        role = Role()
        role.id = uuid.uuid4()
        role.name = name
        role.permissions = []
        roles.append(role)

    user.roles = roles
    return user


def _make_user_with_permissions(*perm_names: str) -> User:
    user = _make_user_with_roles()
    role = Role()
    role.id = uuid.uuid4()
    role.name = "CUSTOM"
    perms = []
    for name in perm_names:
        p = Permission()
        p.id = uuid.uuid4()
        resource, action = name.split(":")
        p.name = name
        p.resource = resource
        p.action = action
        perms.append(p)
    role.permissions = perms
    user.roles = [role]
    return user


# ---------------------------------------------------------------------------
# User model RBAC helpers
# ---------------------------------------------------------------------------


def test_has_role_true():
    user = _make_user_with_roles("ADMIN")
    assert user.has_role("ADMIN")


def test_has_role_false():
    user = _make_user_with_roles("OFFICER")
    assert not user.has_role("ADMIN")


def test_role_names_property():
    user = _make_user_with_roles("ADMIN", "OFFICER")
    assert set(user.role_names) == {"ADMIN", "OFFICER"}


def test_all_permissions_aggregates_across_roles():
    user = _make_user_with_permissions("users:read", "reports:export")
    assert "users:read" in user.all_permissions
    assert "reports:export" in user.all_permissions


def test_has_permission_granted():
    user = _make_user_with_permissions("inventory:write")
    assert user.has_permission("inventory:write")


def test_has_permission_denied():
    user = _make_user_with_permissions("inventory:read")
    assert not user.has_permission("inventory:write")


def test_superuser_has_all_permissions():
    user = _make_user_with_roles(is_superuser=True)
    # Superuser always returns True regardless of actual role permissions
    assert user.has_permission("any:permission")
    assert user.has_permission("users:delete")


# ---------------------------------------------------------------------------
# require_roles dependency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_roles_passes_for_matching_role():
    user = _make_user_with_roles("ADMIN")
    # Call the inner _check directly by constructing it via require_roles
    # require_roles returns a callable that FastAPI wraps; we call it as a coroutine
    dep_callable = require_roles("ADMIN")
    result = await dep_callable(current_user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_roles_raises_for_non_matching_role():
    user = _make_user_with_roles("STORE_KEEPER")
    dep_callable = require_roles("ADMIN")
    with pytest.raises(ForbiddenError):
        await dep_callable(current_user=user)


@pytest.mark.asyncio
async def test_require_roles_passes_for_superuser():
    user = _make_user_with_roles(is_superuser=True)
    dep_callable = require_roles("ADMIN")
    result = await dep_callable(current_user=user)
    assert result is user


# ---------------------------------------------------------------------------
# require_permission dependency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_permission_passes():
    user = _make_user_with_permissions("users:read")
    dep_callable = require_permission("users:read")
    result = await dep_callable(current_user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_permission_denied():
    user = _make_user_with_permissions("users:read")
    dep_callable = require_permission("users:write")
    with pytest.raises(ForbiddenError):
        await dep_callable(current_user=user)


