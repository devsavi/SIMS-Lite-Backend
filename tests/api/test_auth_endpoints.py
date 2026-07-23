"""
API-level tests for authentication endpoints.

Uses the ASGI test client with mocked service dependencies.
No real database or Redis is required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.models.user import Role, User
from app.schemas.auth import TokenResponse


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_user() -> User:
    user = User()
    user.id = uuid.uuid4()
    user.email = "alice@example.com"
    user.first_name = "Alice"
    user.last_name = "Example"
    user.phone = None
    user.is_active = True
    user.is_verified = True
    user.is_superuser = False
    user.last_login = None
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    user.roles = []
    return user


def _mock_token_response() -> TokenResponse:
    return TokenResponse(
        access_token="mock.access.token",
        refresh_token="mock.refresh.token",
        expires_in=1800,
    )


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, app_instance):
    user = _make_user()

    with patch("app.api.v1.endpoints.auth.AuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.register = AsyncMock(return_value=user)

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "alice@example.com",
                "password": "Secret@123!",
                "first_name": "Alice",
                "last_name": "Example",
            },
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient, app_instance):
    with patch("app.api.v1.endpoints.auth.AuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.register = AsyncMock(
            side_effect=ConflictError("Email already exists.")
        )

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "dup@example.com",
                "password": "Secret@123!",
                "first_name": "Alice",
                "last_name": "Example",
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_register_weak_password_returns_422(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "weak",
            "first_name": "Test",
            "last_name": "User",
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    tokens = _mock_token_response()

    with patch("app.api.v1.endpoints.auth.AuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.login = AsyncMock(return_value=tokens)

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "Secret@123!"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["access_token"] == "mock.access.token"
    assert data["data"]["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials_returns_401(client: AsyncClient):
    with patch("app.api.v1.endpoints.auth.AuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.login = AsyncMock(
            side_effect=UnauthorizedError("Invalid email or password.")
        )

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "Wrong@123!"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_login_locked_account_returns_403(client: AsyncClient):
    with patch("app.api.v1.endpoints.auth.AuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.login = AsyncMock(
            side_effect=ForbiddenError("Account is temporarily locked.")
        )

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "Secret@123!"},
        )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_success(client: AsyncClient):
    tokens = _mock_token_response()

    with patch("app.api.v1.endpoints.auth.AuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.refresh = AsyncMock(return_value=tokens)

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "some.valid.token"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["access_token"] == "mock.access.token"


@pytest.mark.asyncio
async def test_refresh_invalid_token_returns_401(client: AsyncClient):
    with patch("app.api.v1.endpoints.auth.AuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.refresh = AsyncMock(
            side_effect=UnauthorizedError("Invalid or expired refresh token.")
        )

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "bad.token"},
        )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/forgot-password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forgot_password_always_200(client: AsyncClient):
    with patch("app.api.v1.endpoints.auth.AuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.forgot_password = AsyncMock()

        response = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )

    assert response.status_code == 200
    assert "registered" in response.json()["data"]["message"].lower()


# ---------------------------------------------------------------------------
# POST /auth/reset-password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_password_success(client: AsyncClient):
    with patch("app.api.v1.endpoints.auth.AuthService") as MockSvc:
        instance = MockSvc.return_value
        instance.reset_password = AsyncMock()

        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "validtoken123", "new_password": "NewPass@123!"},
        )

    assert response.status_code == 200
    assert "reset" in response.json()["data"]["message"].lower()


# ---------------------------------------------------------------------------
# GET /auth/me — requires auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_token(client: AsyncClient, app_instance):
    user = _make_user()

    from app.core.deps import get_current_user
    from app.database.engine import get_db

    original_overrides = dict(app_instance.dependency_overrides)
    app_instance.dependency_overrides[get_current_user] = lambda: user

    try:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer fake.token"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["email"] == "alice@example.com"
    finally:
        # Restore original overrides (don't wipe get_db mock)
        app_instance.dependency_overrides.clear()
        app_instance.dependency_overrides.update(original_overrides)
