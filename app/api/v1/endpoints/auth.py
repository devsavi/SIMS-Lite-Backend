"""
Authentication endpoints.

POST /api/v1/auth/register        — Create new account
POST /api/v1/auth/login           — Issue access + refresh tokens
POST /api/v1/auth/logout          — Revoke refresh token
POST /api/v1/auth/logout-all      — Revoke all refresh tokens (all devices)
POST /api/v1/auth/refresh         — Exchange refresh token for new pair
POST /api/v1/auth/forgot-password — Request password-reset email
POST /api/v1/auth/reset-password  — Set new password via reset token
POST /api/v1/auth/change-password — Change password (authenticated)
GET  /api/v1/auth/verify-email    — Verify email address via token
GET  /api/v1/auth/me              — Return current user info
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_ip, get_current_user
from app.core.exceptions import ValidationError
from app.database.engine import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.base import SuccessResponse
from app.schemas.user import UserRead
from app.services.auth import AuthService

router = APIRouter()


def _auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=SuccessResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    payload: RegisterRequest,
    request: Request,
    svc: AuthService = Depends(_auth_service),
) -> SuccessResponse[UserRead]:
    """
    Create a new user account.

    In production this endpoint should be protected or limited to
    invitation-based flows. For now it is open for development.
    """
    ip = get_client_ip(request)
    ua = request.headers.get("User-Agent")
    user = await svc.register(payload, ip_address=ip, user_agent=ua)
    return SuccessResponse(data=UserRead.model_validate(user))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=SuccessResponse[TokenResponse],
    summary="Authenticate and receive tokens",
)
async def login(
    payload: LoginRequest,
    request: Request,
    svc: AuthService = Depends(_auth_service),
) -> SuccessResponse[TokenResponse]:
    """
    Authenticate with email + password.

    Returns an access token (short-lived) and a refresh token (long-lived).
    Store both securely; send the access token as ``Authorization: Bearer <token>``.
    """
    ip = get_client_ip(request)
    ua = request.headers.get("User-Agent")
    tokens = await svc.login(payload, ip_address=ip, user_agent=ua)
    return SuccessResponse(data=tokens)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post(
    "/logout",
    response_model=SuccessResponse[MessageResponse],
    summary="Revoke the current refresh token",
)
async def logout(
    payload: RefreshTokenRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: AuthService = Depends(_auth_service),
) -> SuccessResponse[MessageResponse]:
    """Revoke the provided refresh token (single-device logout)."""
    ip = get_client_ip(request)
    await svc.logout(current_user, payload.refresh_token, ip_address=ip)
    return SuccessResponse(data=MessageResponse(message="Successfully logged out."))


@router.post(
    "/logout-all",
    response_model=SuccessResponse[MessageResponse],
    summary="Revoke all refresh tokens (all devices)",
)
async def logout_all(
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: AuthService = Depends(_auth_service),
) -> SuccessResponse[MessageResponse]:
    """Revoke every active refresh token for the current user."""
    ip = get_client_ip(request)
    await svc.logout_all(current_user, ip_address=ip)
    return SuccessResponse(
        data=MessageResponse(message="Logged out from all devices.")
    )


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


@router.post(
    "/refresh",
    response_model=SuccessResponse[TokenResponse],
    summary="Exchange a refresh token for a new token pair",
)
async def refresh_tokens(
    payload: RefreshTokenRequest,
    request: Request,
    svc: AuthService = Depends(_auth_service),
) -> SuccessResponse[TokenResponse]:
    """
    Perform refresh token rotation.

    The old refresh token is revoked and a new access + refresh pair is issued.
    """
    ip = get_client_ip(request)
    ua = request.headers.get("User-Agent")
    tokens = await svc.refresh(
        payload.refresh_token, ip_address=ip, user_agent=ua
    )
    return SuccessResponse(data=tokens)


# ---------------------------------------------------------------------------
# Password reset flow
# ---------------------------------------------------------------------------


@router.post(
    "/forgot-password",
    response_model=SuccessResponse[MessageResponse],
    summary="Request a password-reset email",
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    svc: AuthService = Depends(_auth_service),
) -> SuccessResponse[MessageResponse]:
    """
    Send a password-reset email if the address is registered.

    Always returns 200 to prevent user enumeration.
    """
    ip = get_client_ip(request)
    await svc.forgot_password(str(payload.email), ip_address=ip)
    return SuccessResponse(
        data=MessageResponse(
            message="If this email is registered you will receive reset instructions."
        )
    )


@router.post(
    "/reset-password",
    response_model=SuccessResponse[MessageResponse],
    summary="Set a new password using the reset token",
)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    svc: AuthService = Depends(_auth_service),
) -> SuccessResponse[MessageResponse]:
    """Validate the reset token and update the password."""
    ip = get_client_ip(request)
    await svc.reset_password(payload, ip_address=ip)
    return SuccessResponse(
        data=MessageResponse(message="Password has been reset successfully.")
    )


# ---------------------------------------------------------------------------
# Change password (authenticated)
# ---------------------------------------------------------------------------


@router.post(
    "/change-password",
    response_model=SuccessResponse[MessageResponse],
    summary="Change password while authenticated",
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: AuthService = Depends(_auth_service),
) -> SuccessResponse[MessageResponse]:
    """Change the current user's password. Revokes all existing refresh tokens."""
    ip = get_client_ip(request)
    await svc.change_password(current_user, payload, ip_address=ip)
    return SuccessResponse(
        data=MessageResponse(message="Password changed successfully. Please log in again.")
    )


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


@router.get(
    "/verify-email",
    response_model=SuccessResponse[MessageResponse],
    summary="Verify email address via token",
)
async def verify_email(
    token: str,
    svc: AuthService = Depends(_auth_service),
) -> SuccessResponse[MessageResponse]:
    """Mark the account email as verified using the token from the verification email."""
    await svc.verify_email(token)
    return SuccessResponse(
        data=MessageResponse(message="Email verified successfully.")
    )


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=SuccessResponse[UserRead],
    summary="Return the currently authenticated user",
)
async def me(
    current_user: User = Depends(get_current_user),
) -> SuccessResponse[UserRead]:
    """Return full profile for the authenticated user."""
    return SuccessResponse(data=UserRead.model_validate(current_user))
