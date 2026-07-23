"""
Notification ORM models — Phase 6A.

Tables:
    notifications             — persisted notification records
    notification_preferences  — per-user delivery preferences
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NotificationType(str, Enum):
    """Category of the notification."""

    SYSTEM = "SYSTEM"
    SUCCESS = "SUCCESS"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    GRN = "GRN"
    STOCK_RELEASE = "STOCK_RELEASE"
    INVENTORY = "INVENTORY"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    USER = "USER"
    SECURITY = "SECURITY"


class NotificationPriority(str, Enum):
    """Delivery urgency of the notification."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecipientType(str, Enum):
    """Who receives the notification."""

    USER = "USER"       # single user_id
    ROLE = "ROLE"       # all users with a role
    BROADCAST = "BROADCAST"  # everyone


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


class Notification(Base, UUIDMixin, TimestampMixin):
    """
    Persisted notification record.

    Delivery channel (WebSocket / e-mail) is handled by the service
    layer; this table is the source-of-truth for read/unread state.
    """

    __tablename__ = "notifications"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=NotificationType.INFO, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default=NotificationPriority.NORMAL, index=True
    )

    # --- Targeting ---
    recipient_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RecipientType.USER, index=True
    )
    recipient_role: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # --- Sender ---
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # --- Read state ---
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Extra payload (optional structured data for client-side routing) ---
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # --- Relationships ---
    recipient: Mapped[Any] = relationship(
        "User",
        foreign_keys=[recipient_user_id],
        lazy="select",
    )
    sender: Mapped[Any] = relationship(
        "User",
        foreign_keys=[sender_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} type={self.type} "
            f"recipient_type={self.recipient_type} is_read={self.is_read}>"
        )


# ---------------------------------------------------------------------------
# NotificationPreference
# ---------------------------------------------------------------------------


class NotificationPreference(Base, TimestampMixin):
    """Per-user notification delivery preferences (one row per user)."""

    __tablename__ = "notification_preferences"

    # Use user_id as the PK (one-to-one with users)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    enable_websocket: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mute_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Relationship ---
    user: Mapped[Any] = relationship("User", foreign_keys=[user_id], lazy="select")

    def __repr__(self) -> str:
        return (
            f"<NotificationPreference user_id={self.user_id} "
            f"ws={self.enable_websocket} email={self.enable_email}>"
        )
