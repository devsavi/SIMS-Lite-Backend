"""
Notification endpoints — Phase 6A.

Routes:
    GET    /notifications                          — list user notifications (paginated)
    GET    /notifications/unread                   — list unread notifications (paginated)
    PATCH  /notifications/read-all                 — mark all as read
    GET    /notifications/preferences/me           — get user preferences
    PUT    /notifications/preferences/me           — update user preferences
    GET    /notifications/dashboard/unread-count   — unread count widget
    GET    /notifications/dashboard/recent         — recent notifications widget
    GET    /notifications/dashboard/critical-alerts — critical alerts widget
    GET    /notifications/{id}                     — get single notification
    PATCH  /notifications/{id}/read                — mark as read
    DELETE /notifications/{id}                     — delete notification

IMPORTANT: All static-path routes must be registered before /{notification_id}
so that FastAPI does not treat "unread", "read-all", "preferences", and
"dashboard" as UUID path parameters.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database.engine import get_db
from app.models.user import User
from app.schemas.base import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.notification import (
    CriticalAlertsResponse,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationRead,
    RecentNotificationsResponse,
    UnreadCountResponse,
)
from app.services.notification import NotificationService

router = APIRouter()


def _get_svc(db: AsyncSession = Depends(get_db)) -> NotificationService:
    return NotificationService(db)


# ---------------------------------------------------------------------------
# Static routes — MUST come before /{notification_id}
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedResponse[NotificationRead],
    summary="List notifications",
    description=(
        "Return paginated notifications for the current user "
        "(includes user-specific, role-based, and broadcasts)."
    ),
)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> PaginatedResponse[NotificationRead]:
    notifications, total = await svc.list_notifications(
        current_user, page=page, size=size
    )
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=notifications,
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.get(
    "/unread",
    response_model=PaginatedResponse[NotificationRead],
    summary="List unread notifications",
)
async def list_unread_notifications(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> PaginatedResponse[NotificationRead]:
    notifications, total = await svc.list_unread(
        current_user, page=page, size=size
    )
    pages = (total + size - 1) // size if total else 0
    return PaginatedResponse(
        data=notifications,
        pagination=PaginationMeta(page=page, size=size, total=total, pages=pages),
    )


@router.patch(
    "/read-all",
    response_model=SuccessResponse[dict],
    summary="Mark all notifications as read",
)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> SuccessResponse[dict]:
    count = await svc.mark_all_read(current_user)
    return SuccessResponse(data={"marked_read": count})


# ---------------------------------------------------------------------------
# Notification preferences  (static — before /{notification_id})
# ---------------------------------------------------------------------------


@router.get(
    "/preferences/me",
    response_model=SuccessResponse[NotificationPreferenceRead],
    summary="Get my notification preferences",
)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> SuccessResponse[NotificationPreferenceRead]:
    pref = await svc.get_preferences(current_user)
    return SuccessResponse(data=NotificationPreferenceRead.model_validate(pref))


@router.put(
    "/preferences/me",
    response_model=SuccessResponse[NotificationPreferenceRead],
    summary="Update my notification preferences",
)
async def update_preferences(
    payload: NotificationPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> SuccessResponse[NotificationPreferenceRead]:
    pref = await svc.update_preferences(current_user, payload)
    return SuccessResponse(data=NotificationPreferenceRead.model_validate(pref))


# ---------------------------------------------------------------------------
# Dashboard widgets  (static — before /{notification_id})
# ---------------------------------------------------------------------------


@router.get(
    "/dashboard/unread-count",
    response_model=SuccessResponse[UnreadCountResponse],
    summary="Unread notification count (dashboard widget)",
)
async def dashboard_unread_count(
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> SuccessResponse[UnreadCountResponse]:
    result = await svc.get_unread_count(current_user)
    return SuccessResponse(data=result)


@router.get(
    "/dashboard/recent",
    response_model=SuccessResponse[RecentNotificationsResponse],
    summary="Recent notifications (dashboard widget)",
)
async def dashboard_recent(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> SuccessResponse[RecentNotificationsResponse]:
    result = await svc.get_recent_notifications(current_user, limit=limit)
    return SuccessResponse(data=result)


@router.get(
    "/dashboard/critical-alerts",
    response_model=SuccessResponse[CriticalAlertsResponse],
    summary="Critical alerts (dashboard widget)",
)
async def dashboard_critical_alerts(
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> SuccessResponse[CriticalAlertsResponse]:
    result = await svc.get_critical_alerts(current_user)
    return SuccessResponse(data=result)


# ---------------------------------------------------------------------------
# Parameterised routes — MUST come after all static paths above
# ---------------------------------------------------------------------------


@router.get(
    "/{notification_id}",
    response_model=SuccessResponse[NotificationRead],
    summary="Get notification by ID",
)
async def get_notification(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> SuccessResponse[NotificationRead]:
    notification = await svc.get_by_id(notification_id, current_user)
    return SuccessResponse(data=notification)


@router.patch(
    "/{notification_id}/read",
    response_model=SuccessResponse[NotificationRead],
    summary="Mark notification as read",
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> SuccessResponse[NotificationRead]:
    notification = await svc.mark_read(notification_id, current_user)
    return SuccessResponse(data=notification)


@router.delete(
    "/{notification_id}",
    response_model=SuccessResponse[dict],
    summary="Delete a notification",
)
async def delete_notification(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_svc),
) -> SuccessResponse[dict]:
    await svc.delete_notification(notification_id, current_user)
    return SuccessResponse(data={"deleted": True})
