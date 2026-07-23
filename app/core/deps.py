"""
FastAPI dependency functions for authentication and authorisation.

Usage in route handlers::

    # Require any authenticated user
    @router.get("/me")
    async def me(current_user: User = Depends(get_current_user)):
        ...

    # Require a specific role
    @router.get("/admin")
    async def admin_only(current_user: User = Depends(require_roles("ADMIN"))):
        ...

    # Require a specific permission
    @router.post("/users")
    async def create(current_user: User = Depends(require_permission("users:write"))):
        ...
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import decode_token
from app.database.engine import get_db
from app.models.user import User
from app.repositories.user import UserRepository

logger = get_logger(__name__)

# Use HTTPBearer so Swagger UI shows the "Authorize" button
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Decode the Bearer JWT, look up the user, and return it.

    Raises UnauthorizedError if the token is missing, invalid,
    expired, or the user no longer exists / is inactive.
    """
    if credentials is None:
        raise UnauthorizedError("Missing authentication token.")

    try:
        claims = decode_token(credentials.credentials)
    except JWTError:
        raise UnauthorizedError("Invalid or expired access token.")

    if claims.get("type") != "access":
        raise UnauthorizedError("Token is not an access token.")

    user_id_str: str | None = claims.get("sub")
    if not user_id_str:
        raise UnauthorizedError("Token subject is missing.")

    import uuid

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedError("Token subject is invalid.")

    repo = UserRepository(db)
    user = await repo.get_by_id_with_roles(user_id)

    if user is None:
        raise UnauthorizedError("User not found.")
    if not user.is_active:
        raise ForbiddenError("Account is deactivated.")

    return user


def require_roles(*role_names: str) -> Callable:
    """
    Return a dependency that asserts the current user has at least one
    of the listed roles (or is a superuser).

    Usage::

        Depends(require_roles("ADMIN"))
        Depends(require_roles("ADMIN", "OFFICER"))
    """

    async def _check(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.is_superuser:
            return current_user
        if not any(current_user.has_role(r) for r in role_names):
            raise ForbiddenError(
                f"Required role(s): {', '.join(role_names)}."
            )
        return current_user

    return _check


def require_permission(permission: str) -> Callable:
    """
    Return a dependency that asserts the current user has the given
    permission (or is a superuser).

    Usage::

        Depends(require_permission("users:write"))
    """

    async def _check(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if not current_user.has_permission(permission):
            raise ForbiddenError(
                f"Required permission: {permission}."
            )
        return current_user

    return _check


def require_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency: only superusers may proceed."""
    if not current_user.is_superuser:
        raise ForbiddenError("Superuser access required.")
    return current_user


def get_client_ip(request: Request) -> str | None:
    """Extract the client IP from X-Forwarded-For or the direct connection."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
