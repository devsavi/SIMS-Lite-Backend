"""
Authentication request/response schemas.

These Pydantic models define the contract for every auth endpoint.
Input schemas validate and sanitise incoming data; output schemas
define exactly what the API surface exposes.
"""

from __future__ import annotations

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import AppBaseModel


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class LoginRequest(AppBaseModel):
    """Credentials submitted to POST /auth/login."""

    email: EmailStr
    password: str = Field(min_length=1)


class RefreshTokenRequest(AppBaseModel):
    """Refresh token submitted to POST /auth/refresh."""

    refresh_token: str = Field(min_length=1)


class RegisterRequest(AppBaseModel):
    """
    New account registration payload.

    POST /auth/register — open in development; restricted in production.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Enforce basic password complexity rules."""
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


class ForgotPasswordRequest(AppBaseModel):
    """Email address submitted to POST /auth/forgot-password."""

    email: EmailStr


class ResetPasswordRequest(AppBaseModel):
    """New password + reset token submitted to POST /auth/reset-password."""

    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
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


class ChangePasswordRequest(AppBaseModel):
    """Old + new password submitted to POST /auth/change-password."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
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


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TokenResponse(AppBaseModel):
    """Pair of access + refresh tokens returned after login or refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expiry


class MessageResponse(AppBaseModel):
    """Generic single-message acknowledgement."""

    message: str
