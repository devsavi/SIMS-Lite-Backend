"""
Authentication service.

Handles:
- User registration
- Login with brute-force protection
- JWT access token issuance
- Refresh token rotation
- Logout (single device and all devices)
- Password reset flow
- Email verification
- Password change
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.repositories.audit_log import AuditLogRepository
from app.repositories.user import RefreshTokenRepository, RoleRepository, UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services.email import email_service

logger = get_logger(__name__)

# Number of failed logins before locking the account
MAX_FAILED_ATTEMPTS = 5
# How long the account lock lasts (minutes)
LOCK_DURATION_MINUTES = 15
# Password-reset token validity (minutes)
RESET_TOKEN_EXPIRE_MINUTES = 60
# Prefix for Redis token blacklist keys
BLACKLIST_PREFIX = "jwt:blacklist:"


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash a raw token for safe storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


class AuthService:
    """All authentication business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._tokens = RefreshTokenRepository(session)
        self._roles = RoleRepository(session)
        self._audit = AuditLogRepository(session)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(
        self,
        payload: RegisterRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
        default_role: str = "OFFICER",
    ) -> User:
        """
        Create a new user account.

        Assigns the default role and sends a verification email.
        Raises ConflictError if the email is already in use.
        """
        email = payload.email.lower().strip()
        if await self._users.email_exists(email):
            raise ConflictError(f"An account with email '{email}' already exists.")

        password_hash = hash_password(payload.password)
        verification_token = secrets.token_urlsafe(32)

        user = await self._users.create(
            email=email,
            password_hash=password_hash,
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            phone=payload.phone,
            email_verification_token=verification_token,
        )

        # Assign default role
        role = await self._roles.get_by_name(default_role)
        if role:
            user.roles.append(role)
            self._session.add(user)
            await self._session.flush()
            await self._session.refresh(user)

        await self._audit.log(
            action="auth.register",
            actor_id=user.id,
            resource_type="User",
            resource_id=str(user.id),
            ip_address=ip_address,
            user_agent=user_agent,
            detail={"email": email},
        )

        # Best-effort — don't fail registration if email fails
        try:
            verify_url = (
                f"{settings.app_host}:{settings.app_port}"
                f"/api/v1/auth/verify-email?token={verification_token}"
            )
            await email_service.send_email_verification(
                to_email=email,
                verify_url=verify_url,
            )
        except Exception:
            logger.warning("Verification email failed to send", email=email)

        logger.info("User registered", user_id=str(user.id), email=email)
        return user

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(
        self,
        payload: LoginRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Authenticate a user and issue access + refresh tokens.

        Raises:
            UnauthorizedError: Invalid credentials or inactive account.
            ForbiddenError: Account is locked.
        """
        email = payload.email.lower().strip()
        user = await self._users.get_by_email(email)

        async def _fail(reason: str, user_obj: User | None = None) -> None:
            if user_obj is not None:
                await self._users.increment_failed_logins(user_obj)
                if user_obj.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                    user_obj.locked_until = datetime.now(UTC) + timedelta(
                        minutes=LOCK_DURATION_MINUTES
                    )
                    self._session.add(user_obj)
                    await self._session.flush()
            await self._audit.log(
                action="auth.login",
                status="failure",
                actor_id=user_obj.id if user_obj else None,
                ip_address=ip_address,
                user_agent=user_agent,
                detail={"reason": reason, "email": email},
            )

        if user is None:
            await _fail("user_not_found")
            raise UnauthorizedError("Invalid email or password.")

        # Check account lock
        if user.locked_until and datetime.now(UTC) < user.locked_until:
            remaining = int((user.locked_until - datetime.now(UTC)).total_seconds() / 60)
            await _fail("account_locked", user)
            raise ForbiddenError(
                f"Account is temporarily locked. Try again in {remaining} minute(s)."
            )

        if not verify_password(payload.password, user.password_hash):
            await _fail("wrong_password", user)
            raise UnauthorizedError("Invalid email or password.")

        if not user.is_active:
            await _fail("account_inactive", user)
            raise ForbiddenError("Your account has been deactivated. Contact support.")

        # Successful login — reset counters
        await self._users.reset_failed_logins(user)
        user.last_login = datetime.now(UTC)
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)

        tokens = await self._issue_tokens(user, ip_address=ip_address, user_agent=user_agent)

        await self._audit.log(
            action="auth.login",
            actor_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="User",
            resource_id=str(user.id),
        )

        logger.info("User logged in", user_id=str(user.id), email=email)
        return tokens

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    async def logout(
        self,
        user: User,
        refresh_token: str,
        *,
        ip_address: str | None = None,
    ) -> None:
        """Revoke the provided refresh token."""
        token_hash = _hash_token(refresh_token)
        db_token = await self._tokens.get_by_hash(token_hash)
        if db_token and not db_token.is_revoked:
            db_token.is_revoked = True
            self._session.add(db_token)
            await self._session.flush()

        await self._audit.log(
            action="auth.logout",
            actor_id=user.id,
            ip_address=ip_address,
            resource_type="User",
            resource_id=str(user.id),
        )

    async def logout_all(
        self,
        user: User,
        *,
        ip_address: str | None = None,
    ) -> None:
        """Revoke all refresh tokens for this user (logout from all devices)."""
        revoked = await self._tokens.revoke_all_for_user(user.id)
        await self._audit.log(
            action="auth.logout_all",
            actor_id=user.id,
            ip_address=ip_address,
            resource_type="User",
            resource_id=str(user.id),
            detail={"tokens_revoked": revoked},
        )

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    async def refresh(
        self,
        raw_refresh_token: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Validate the refresh token, revoke it, issue a new pair.

        Implements strict token rotation — every use invalidates
        the previous token.
        """
        from jose import JWTError

        try:
            claims = decode_token(raw_refresh_token)
        except JWTError:
            raise UnauthorizedError("Invalid or expired refresh token.")

        if claims.get("type") != "refresh":
            raise UnauthorizedError("Token is not a refresh token.")

        token_hash = _hash_token(raw_refresh_token)
        db_token = await self._tokens.get_by_hash(token_hash)

        if db_token is None or db_token.is_revoked or not db_token.is_valid:
            raise UnauthorizedError("Refresh token has been revoked or has expired.")

        # Revoke the used token (rotation)
        db_token.is_revoked = True
        self._session.add(db_token)
        await self._session.flush()

        user = await self._users.get_by_id_with_roles(db_token.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("User account is inactive.")

        tokens = await self._issue_tokens(
            user, ip_address=ip_address, user_agent=user_agent
        )

        await self._audit.log(
            action="auth.token_refresh",
            actor_id=user.id,
            ip_address=ip_address,
            resource_type="User",
            resource_id=str(user.id),
        )

        return tokens

    # ------------------------------------------------------------------
    # Password reset
    # ------------------------------------------------------------------

    async def forgot_password(
        self,
        email: str,
        *,
        ip_address: str | None = None,
    ) -> None:
        """
        Initiate password reset.

        Always returns 200 regardless of whether the email exists
        (prevents user enumeration).
        """
        email = email.lower().strip()
        user = await self._users.get_by_email(email)

        if user and user.is_active:
            reset_token = secrets.token_urlsafe(32)
            user.password_reset_token = reset_token
            user.password_reset_expires = datetime.now(UTC) + timedelta(
                minutes=RESET_TOKEN_EXPIRE_MINUTES
            )
            self._session.add(user)
            await self._session.flush()

            reset_url = (
                f"http://localhost:3000/reset-password?token={reset_token}"
            )
            try:
                await email_service.send_password_reset(
                    to_email=email,
                    reset_url=reset_url,
                    expires_minutes=RESET_TOKEN_EXPIRE_MINUTES,
                )
            except Exception:
                logger.warning("Password reset email failed", email=email)

            await self._audit.log(
                action="auth.forgot_password",
                actor_id=user.id,
                ip_address=ip_address,
                resource_type="User",
                resource_id=str(user.id),
            )

    async def reset_password(
        self,
        payload: ResetPasswordRequest,
        *,
        ip_address: str | None = None,
    ) -> None:
        """Validate the reset token and set the new password."""
        user = await self._users.get_by_reset_token(payload.token)

        if user is None:
            raise UnauthorizedError("Invalid or expired password reset token.")

        if (
            user.password_reset_expires is None
            or datetime.now(UTC) > user.password_reset_expires
        ):
            raise UnauthorizedError("Password reset token has expired.")

        user.password_hash = hash_password(payload.new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        self._session.add(user)
        await self._session.flush()

        # Revoke all existing refresh tokens (security measure)
        await self._tokens.revoke_all_for_user(user.id)

        await self._audit.log(
            action="auth.reset_password",
            actor_id=user.id,
            ip_address=ip_address,
            resource_type="User",
            resource_id=str(user.id),
        )

        logger.info("Password reset", user_id=str(user.id))

    # ------------------------------------------------------------------
    # Change password (authenticated)
    # ------------------------------------------------------------------

    async def change_password(
        self,
        user: User,
        payload: ChangePasswordRequest,
        *,
        ip_address: str | None = None,
    ) -> None:
        """Verify current password then set a new one."""
        if not verify_password(payload.current_password, user.password_hash):
            raise ValidationError("Current password is incorrect.")

        if payload.current_password == payload.new_password:
            raise ValidationError("New password must be different from current password.")

        user.password_hash = hash_password(payload.new_password)
        self._session.add(user)
        await self._session.flush()

        # Revoke all refresh tokens to force re-login
        await self._tokens.revoke_all_for_user(user.id)

        await self._audit.log(
            action="auth.change_password",
            actor_id=user.id,
            ip_address=ip_address,
            resource_type="User",
            resource_id=str(user.id),
        )

    # ------------------------------------------------------------------
    # Email verification
    # ------------------------------------------------------------------

    async def verify_email(self, token: str) -> None:
        """Mark the user's email as verified."""
        user = await self._users.get_by_verification_token(token)
        if user is None:
            raise UnauthorizedError("Invalid or expired verification token.")

        user.is_verified = True
        user.email_verification_token = None
        self._session.add(user)
        await self._session.flush()

        await self._audit.log(
            action="auth.verify_email",
            actor_id=user.id,
            resource_type="User",
            resource_id=str(user.id),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _issue_tokens(
        self,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        Create access + refresh tokens and persist the refresh token.
        """
        role_names = [r.name for r in user.roles]
        extra_claims: dict[str, Any] = {
            "email": user.email,
            "roles": role_names,
            "is_superuser": user.is_superuser,
        }

        raw_access = create_access_token(str(user.id), extra_claims=extra_claims)
        raw_refresh = create_refresh_token(str(user.id))

        # Persist hashed refresh token
        await self._tokens.create(
            user_id=user.id,
            token_hash=_hash_token(raw_refresh),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.jwt.refresh_token_expire_days),
            device_info=user_agent,
            ip_address=ip_address,
        )

        # Clean up expired tokens for this user (housekeeping)
        await self._tokens.delete_expired(user.id)

        return TokenResponse(
            access_token=raw_access,
            refresh_token=raw_refresh,
            expires_in=settings.jwt.access_token_expire_minutes * 60,
        )
