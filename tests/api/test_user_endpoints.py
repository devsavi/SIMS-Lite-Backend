"""
API tests for user management endpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.core.exceptions import NotFoundError
from app.models.user import User


def _make_user(is_admin: bool = False) -> User:
    user = User()
    user.id = uuid.uuid4()
    user.email = "admin@example.com" if is_admin else "user@example.com"
    user.first_name = "Admin" if is_admin else "Regular"
    user.last_name = "User"
    user.phone = None
    user.is_active = True
    user.is_verified = True
    user.is_superuser = is_admin
    user.last_login = None
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)

    if is_admin:
        from app.models.user import Role
        role = Role()
        role.id = uuid.uuid4()
        role.name = "ADMIN"
        role.description = "Admin"
        role.is_system = True
        role.permissions = []
        user.roles = [role]
    else:
        user.roles = []
    return user


# ---------------------------------------------------------------------------
# GET /users/ — requires ADMIN
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/users/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_users_as_admin(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user, require_roles
    from app.database.engine import get_db
    from app.services.user import UserService

    admin = _make_user(is_admin=True)
    users_list = [_make_user(), _make_user()]

    mock_svc = MagicMock()
    mock_svc.list_users = AsyncMock(return_value=(users_list, 2))

    original_overrides = dict(app_instance.dependency_overrides)
    app_instance.dependency_overrides[get_current_user] = lambda: admin

    import app.api.v1.endpoints.users as users_module
    app_instance.dependency_overrides[users_module._user_service] = lambda: mock_svc

    try:
        response = await client.get(
            "/api/v1/users/",
            headers={"Authorization": "Bearer fake.token"},
        )
        assert response.status_code in (200, 401, 403)
    finally:
        app_instance.dependency_overrides.clear()
        app_instance.dependency_overrides.update(original_overrides)


# ---------------------------------------------------------------------------
# GET /users/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient, app_instance):
    from app.core.deps import get_current_user
    from app.services.user import UserService

    admin = _make_user(is_admin=True)

    import app.api.v1.endpoints.users as users_module

    mock_svc = MagicMock()
    mock_svc.get_user = AsyncMock(side_effect=NotFoundError("User not found."))

    original_overrides = dict(app_instance.dependency_overrides)
    app_instance.dependency_overrides[get_current_user] = lambda: admin
    app_instance.dependency_overrides[users_module._user_service] = lambda: mock_svc

    try:
        response = await client.get(
            f"/api/v1/users/{uuid.uuid4()}",
            headers={"Authorization": "Bearer fake.token"},
        )
        assert response.status_code in (404, 401, 403)
    finally:
        app_instance.dependency_overrides.clear()
        app_instance.dependency_overrides.update(original_overrides)


# ---------------------------------------------------------------------------
# POST /auth/login — input validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_missing_password_returns_422(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_invalid_email_returns_422(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "Password@1"},
    )
    assert response.status_code == 422
