"""
Unit tests for UserService.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.models.user import Role, User
from app.schemas.user import UserAdminUpdate, UserCreate, UserUpdate
from app.services.user import UserService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    is_superuser: bool = False,
    is_active: bool = True,
) -> User:
    user = User()
    user.id = uuid.uuid4()
    user.email = "user@test.com"
    user.first_name = "Test"
    user.last_name = "User"
    user.phone = None
    user.is_active = is_active
    user.is_superuser = is_superuser
    user.is_verified = True
    user.failed_login_attempts = 0
    user.roles = []
    return user


def _make_service() -> UserService:
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    svc = UserService.__new__(UserService)
    svc._session = mock_session
    svc._users = AsyncMock()
    svc._roles = AsyncMock()
    svc._audit = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_success():
    svc = _make_service()
    actor = _make_user(is_superuser=True)
    new_user = _make_user()
    svc._users.email_exists.return_value = False
    svc._users.create.return_value = new_user
    svc._roles.get_by_ids.return_value = []

    with patch("app.services.user.hash_password", return_value="hashed"):
        result = await svc.create_user(
            UserCreate(
                email="new@example.com",
                password="Secret@123!",
                first_name="Alice",
                last_name="Smith",
            ),
            actor=actor,
        )
    assert result is new_user


@pytest.mark.asyncio
async def test_create_user_duplicate_email_raises_conflict():
    svc = _make_service()
    actor = _make_user(is_superuser=True)
    svc._users.email_exists.return_value = True

    with pytest.raises(ConflictError):
        await svc.create_user(
            UserCreate(
                email="dup@example.com",
                password="Secret@123!",
                first_name="Alice",
                last_name="Smith",
            ),
            actor=actor,
        )


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_not_found_raises():
    svc = _make_service()
    svc._users.get_by_id_with_roles.return_value = None

    with pytest.raises(NotFoundError):
        await svc.get_user(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_user_returns_user():
    svc = _make_service()
    user = _make_user()
    svc._users.get_by_id_with_roles.return_value = user

    result = await svc.get_user(user.id)
    assert result is user


# ---------------------------------------------------------------------------
# update_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_profile_changes_name():
    svc = _make_service()
    user = _make_user()
    updated = _make_user()
    updated.first_name = "NewFirst"
    updated.last_name = "NewLast"
    svc._users.update.return_value = updated

    result = await svc.update_profile(
        user, UserUpdate(first_name="NewFirst", last_name="NewLast")
    )
    assert result.first_name == "NewFirst"


@pytest.mark.asyncio
async def test_update_profile_no_changes_skips_update():
    svc = _make_service()
    user = _make_user()

    result = await svc.update_profile(user, UserUpdate())
    svc._users.update.assert_not_called()


# ---------------------------------------------------------------------------
# activate / deactivate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_self_raises_forbidden():
    svc = _make_service()
    actor = _make_user()
    svc._users.get_by_id_with_roles.return_value = actor

    with pytest.raises(ForbiddenError):
        await svc.deactivate_user(actor.id, actor=actor)


@pytest.mark.asyncio
async def test_deactivate_superuser_raises_forbidden():
    svc = _make_service()
    actor = _make_user(is_superuser=True)
    target = _make_user(is_superuser=True)
    svc._users.get_by_id_with_roles.return_value = target

    with pytest.raises(ForbiddenError):
        await svc.deactivate_user(target.id, actor=actor)


@pytest.mark.asyncio
async def test_deactivate_regular_user_succeeds():
    svc = _make_service()
    actor = _make_user(is_superuser=True)
    target = _make_user()
    deactivated = _make_user(is_active=False)
    svc._users.get_by_id_with_roles.return_value = target
    svc._users.update.return_value = deactivated

    result = await svc.deactivate_user(target.id, actor=actor)
    assert not result.is_active


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_self_raises_forbidden():
    svc = _make_service()
    actor = _make_user(is_superuser=True)
    svc._users.get_by_id_with_roles.return_value = actor

    with pytest.raises(ForbiddenError):
        await svc.delete_user(actor.id, actor=actor)


@pytest.mark.asyncio
async def test_delete_superuser_raises_forbidden():
    svc = _make_service()
    actor = _make_user()
    target = _make_user(is_superuser=True)
    svc._users.get_by_id_with_roles.return_value = target

    with pytest.raises(ForbiddenError):
        await svc.delete_user(target.id, actor=actor)
