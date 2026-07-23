"""
Notification Pydantic schemas — Phase 6A.

Input / output schemas for:
  - Notification CRUD
  - Notification preferences
  - Admin broadcast / targeted send
  - Dashboard widgets
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.models.notification import NotificationPriority, NotificationType, RecipientType
from app.schemas.base import AppBaseModel


# ---------------------------------------------------------------------------
# Notification read schemas
# ---------------------------------------------------------------------------


class NotificationRead(AppBaseModel):
    """Full public view of a notification record."""

    id: uuid.UUID
    title: str
    message: str
    type: str
    priority: str
    recipient_type: str
    recipient_role: str | None
    recipient_user_id: uuid.UUID | None
    sender_id: uuid.UUID | None
    is_read: bool
    read_at: datetime | None
    data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class NotificationSummary(AppBaseModel):
    """Lightweight notification view for lists."""

    id: uuid.UUID
    title: str
    message: str
    type: str
    priority: str
    is_read: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Notification create (internal / system use)
# ---------------------------------------------------------------------------


class NotificationCreate(AppBaseModel):
    """Payload to create a notification (service-level, not exposed directly)."""

    title: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    type: NotificationType = NotificationType.INFO
    priority: NotificationPriority = NotificationPriority.NORMAL
    recipient_type: RecipientType = RecipientType.USER
    recipient_role: str | None = None
    recipient_user_id: uuid.UUID | None = None
    sender_id: uuid.UUID | None = None
    data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Admin send notification
# ---------------------------------------------------------------------------


class AdminNotificationSend(AppBaseModel):
    """
    Payload for the POST /admin/notifications/send endpoint.

    Exactly one of recipient_user_id, recipient_role, or broadcast_all
    must be set.
    """

    title: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    type: NotificationType = NotificationType.INFO
    priority: NotificationPriority = NotificationPriority.NORMAL

    # Targeting — provide exactly one
    recipient_user_id: uuid.UUID | None = None
    recipient_role: str | None = None
    broadcast_all: bool = False

    data: dict[str, Any] | None = None

    @model_validator(mode="after")
    def check_exactly_one_target(self) -> "AdminNotificationSend":
        targets = [
            self.recipient_user_id is not None,
            self.recipient_role is not None,
            self.broadcast_all,
        ]
        if sum(targets) != 1:
            raise ValueError(
                "Exactly one of recipient_user_id, recipient_role, or "
                "broadcast_all must be provided."
            )
        return self


# ---------------------------------------------------------------------------
# Notification preferences
# ---------------------------------------------------------------------------


class NotificationPreferenceRead(AppBaseModel):
    """Public view of a user's notification preferences."""

    user_id: uuid.UUID
    enable_websocket: bool
    enable_email: bool
    enable_system: bool
    mute_until: datetime | None
    updated_at: datetime


class NotificationPreferenceUpdate(AppBaseModel):
    """Payload to update notification preferences."""

    enable_websocket: bool | None = None
    enable_email: bool | None = None
    enable_system: bool | None = None
    mute_until: datetime | None = None


# ---------------------------------------------------------------------------
# Dashboard / widget schemas
# ---------------------------------------------------------------------------


class UnreadCountResponse(AppBaseModel):
    """Response for the unread notification count widget."""

    unread_count: int
    critical_count: int
    high_count: int


class RecentNotificationsResponse(AppBaseModel):
    """Response for the recent-notifications dashboard widget."""

    notifications: list[NotificationSummary]
    unread_count: int


class CriticalAlertsResponse(AppBaseModel):
    """Response for the critical-alerts dashboard widget."""

    alerts: list[NotificationSummary]
    total: int
