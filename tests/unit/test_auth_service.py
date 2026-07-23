"""
Unit tests for AuthService.

All database calls are mocked — these tests run without a live DB or Redis.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt as _bcrypt_lib
import pytest

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
    ValidationError,
)
from app.models.user import RefreshToken, Role, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.services.auth import MAX_FAILED_ATTEMPTS, AuthService, _hash_token


# ---------------------------------------------------------------------------
# Helpers — use raw bcrypt to bypass passlib version detection issues
# ---------------------------------------------------------------------------


def _bcrypt_hash(password: str) -> str:
    """Hash using raw bcrypt library to avoid passlib/bcrypt version mismatch."""
    return _bcrypt_lib.hashpw(
        password.encode("utf-8"), _bcrypt_lib.gensalt(rounds=4)  # rounds=4 for speed
    ).decode("utf-8")


def _make_user(
    *,
    email: str = "test@example.com",
    password: str = "Secret@123",
    is_active: bool = True,
    is_superuser: bool = False,
    failed_attempts: int = 0,
    locked_until: datetime | None = None,
) -> User:
    user = User()
    user.id = uuid.uuid4()
    user.email = email
    user.password_hash = _bcrypt_hash(password)
    user.first_name = "Test"
    user.last_name = "User"
    user.is_active = is_active
    user.is_superuser = is_superuser
    user.is_verified = True
    user.failed_login_attempts = failed_attempts
    user.locked_until = locked_until
    user.roles = []
    user.refresh_tokens = []
    return user


def _make_service() -> tuple[AuthService, MagicMock]:
    """Return (service, mock_session) with pre-wired repository mocks."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    svc = AuthService.__new__(AuthService)
    svc._session = mock_session
    svc._users = AsyncMock()
    svc._tokens = AsyncMock()
    svc._roles = AsyncMock()
    svc._audit = AsyncMock()
    return svc, mock_session


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_success():
    svc, _ = _make_service()
    user = _make_user()
    svc._users.email_exists.return_value = False
    svc._users.create.return_value = user
    svc._roles.get_by_name.return_value = None

    with patch("app.services.auth.email_service") as mock_email:
        mock_email.send_email_verification = AsyncMock()
        # Also patch hash_password to avoid passlib/bcrypt compat issues
        with patch("app.services.auth.hash_password", return_value="hashed"):
            result = await svc.register(
                RegisterRequest(
                    email="new@example.com",
                    password="Secret@123!",
                    first_name="Alice",
                    last_name="Smith",
                )
            )

    svc._users.create.assert_called_once()
    assert result is user


@pytest.mark.asyncio
async def test_register_duplicate_email_raises_conflict():
    svc, _ = _make_service()
    svc._users.email_exists.return_value = True

    with pytest.raises(ConflictError):
        await svc.register(
            RegisterRequest(
                email="existing@example.com",
                password="Secret@123!",
                first_name="Alice",
                last_name="Smith",
            )
        )


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success():
    svc, _ = _make_service()
    password = "Secret@123!"
    user = _make_user(password=password)
    svc._users.get_by_email.return_value = user
    svc._users.reset_failed_logins.return_value = user

    with patch("app.services.auth.verify_password", return_value=True):
        with patch.object(svc, "_issue_tokens", new=AsyncMock(return_value=MagicMock())):
            result = await svc.login(
                LoginRequest(email="test@example.com", password=password)
            )

    assert result is not None


@pytest.mark.asyncio
async def test_login_wrong_password_raises_unauthorized():
    svc, _ = _make_service()
    user = _make_user(password="Secret@123!")
    svc._users.get_by_email.return_value = user
    svc._users.increment_failed_logins.return_value = user

    with patch("app.services.auth.verify_password", return_value=False):
        with pytest.raises(UnauthorizedError):
            await svc.login(
                LoginRequest(email="test@example.com", password="WrongPass@1")
            )


@pytest.mark.asyncio
async def test_login_unknown_email_raises_unauthorized():
    svc, _ = _make_service()
    svc._users.get_by_email.return_value = None

    with pytest.raises(UnauthorizedError):
        await svc.login(LoginRequest(email="ghost@example.com", password="Secret@1"))


@pytest.mark.asyncio
async def test_login_inactive_user_raises_forbidden():
    svc, _ = _make_service()
    user = _make_user(password="Secret@123!", is_active=False)
    svc._users.get_by_email.return_value = user
    svc._users.reset_failed_logins.return_value = user
    svc._users.increment_failed_logins.return_value = user

    with patch("app.services.auth.verify_password", return_value=True):
        with pytest.raises(ForbiddenError):
            await svc.login(
                LoginRequest(email="test@example.com", password="Secret@123!")
            )


@pytest.mark.asyncio
async def test_login_locked_account_raises_forbidden():
    svc, _ = _make_service()
    user = _make_user(
        locked_until=datetime.now(UTC) + timedelta(minutes=10)
    )
    svc._users.get_by_email.return_value = user
    svc._users.increment_failed_logins.return_value = user

    with pytest.raises(ForbiddenError, match="locked"):
        await svc.login(LoginRequest(email="test@example.com", password="any"))


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_invalid_token_raises_unauthorized():
    svc, _ = _make_service()

    with pytest.raises(UnauthorizedError):
        await svc.refresh("not.a.valid.token")


@pytest.mark.asyncio
async def test_refresh_revoked_token_raises_unauthorized():
    svc, _ = _make_service()

    with patch("app.services.auth.decode_token") as mock_decode:
        mock_decode.return_value = {"type": "refresh", "sub": str(uuid.uuid4())}
        revoked = MagicMock()
        revoked.is_revoked = True
        revoked.is_valid = False
        svc._tokens.get_by_hash.return_value = revoked

        with pytest.raises(UnauthorizedError):
            await svc.refresh("some.refresh.token")


# ---------------------------------------------------------------------------
# forgot_password / reset_password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forgot_password_does_not_reveal_unknown_email():
    """Endpoint must not error on unknown email (prevent enumeration)."""
    svc, _ = _make_service()
    svc._users.get_by_email.return_value = None

    # Should not raise
    await svc.forgot_password("nobody@example.com")


@pytest.mark.asyncio
async def test_reset_password_invalid_token_raises_unauthorized():
    svc, _ = _make_service()
    svc._users.get_by_reset_token.return_value = None

    with pytest.raises(UnauthorizedError):
        await svc.reset_password(
            ResetPasswordRequest(token="badtoken", new_password="NewPass@1!")
        )


@pytest.mark.asyncio
async def test_reset_password_expired_token_raises_unauthorized():
    svc, _ = _make_service()
    user = _make_user()
    user.password_reset_token = "validtoken"
    user.password_reset_expires = datetime.now(UTC) - timedelta(minutes=1)  # expired
    svc._users.get_by_reset_token.return_value = user

    with pytest.raises(UnauthorizedError, match="expired"):
        await svc.reset_password(
            ResetPasswordRequest(token="validtoken", new_password="NewPass@1!")
        )


# ---------------------------------------------------------------------------
# change_password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_password_wrong_current_raises_validation():
    svc, _ = _make_service()
    user = _make_user(password="Current@1!")

    with patch("app.services.auth.verify_password", return_value=False):
        with pytest.raises(ValidationError, match="Current password"):
            await svc.change_password(
                user,
                ChangePasswordRequest(
                    current_password="Wrong@123!", new_password="New@Pass1!"
                ),
            )


@pytest.mark.asyncio
async def test_change_password_same_as_current_raises_validation():
    svc, _ = _make_service()
    user = _make_user(password="Same@Pass1!")

    with patch("app.services.auth.verify_password", return_value=True):
        with pytest.raises(ValidationError, match="different"):
            await svc.change_password(
                user,
                ChangePasswordRequest(
                    current_password="Same@Pass1!", new_password="Same@Pass1!"
                ),
            )


# ---------------------------------------------------------------------------
# _hash_token
# ---------------------------------------------------------------------------


def test_hash_token_is_deterministic():
    raw = "my-secret-token"
    assert _hash_token(raw) == _hash_token(raw)


def test_hash_token_sha256():
    raw = "test"
    expected = hashlib.sha256(b"test").hexdigest()
    assert _hash_token(raw) == expected
