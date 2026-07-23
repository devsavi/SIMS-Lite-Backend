"""
Notification repository — Phase 6A.

Domain-specific database queries for notifications and preferences.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    Notification,
    NotificationPreference,
    NotificationPriority,
    RecipientType,
)
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Queries for the ``notifications`` table."""

    model = Notification

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    async def get_for_user(
        self,
        user_id: uuid.UUID,
        user_role: str | None = None,
        *,
        offset: int = 0,
        limit: int = 20,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        """
        Return (notifications, total) visible to a specific user.

        Includes:
          - USER notifications addressed directly to this user
          - ROLE notifications for the user's role (if provided)
          - BROADCAST notifications
        """
        conditions = [
            or_(
                and_(
                    Notification.recipient_type == RecipientType.USER,
                    Notification.recipient_user_id == user_id,
                ),
                Notification.recipient_type == RecipientType.BROADCAST,
                *(
                    [
                        and_(
                            Notification.recipient_type == RecipientType.ROLE,
                            Notification.recipient_role == user_role,
                        )
                    ]
                    if user_role
                    else []
                ),
            )
        ]

        if unread_only:
            conditions.append(Notification.is_read == False)  # noqa: E712

        base_query = select(Notification).where(*conditions)

        count_result = await self.session.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = count_result.scalar_one()

        result = await self.session.execute(
            base_query.order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_unread_for_user(
        self,
        user_id: uuid.UUID,
        user_role: str | None = None,
    ) -> list[Notification]:
        """Return all unread notifications for a user (no pagination)."""
        notifications, _ = await self.get_for_user(
            user_id, user_role, offset=0, limit=1000, unread_only=True
        )
        return notifications

    async def count_unread(
        self,
        user_id: uuid.UUID,
        user_role: str | None = None,
    ) -> dict[str, int]:
        """Return unread counts: total, critical, high."""
        all_unread = await self.get_unread_for_user(user_id, user_role)
        critical = sum(
            1 for n in all_unread if n.priority == NotificationPriority.CRITICAL
        )
        high = sum(1 for n in all_unread if n.priority == NotificationPriority.HIGH)
        return {
            "unread_count": len(all_unread),
            "critical_count": critical,
            "high_count": high,
        }

    async def get_recent_for_user(
        self,
        user_id: uuid.UUID,
        user_role: str | None = None,
        limit: int = 10,
    ) -> list[Notification]:
        """Return the most recent notifications for dashboard widget."""
        notifications, _ = await self.get_for_user(
            user_id, user_role, offset=0, limit=limit
        )
        return notifications

    async def get_critical_alerts(
        self,
        user_id: uuid.UUID,
        user_role: str | None = None,
        limit: int = 20,
    ) -> tuple[list[Notification], int]:
        """Return critical/high-priority unread notifications."""
        unread = await self.get_unread_for_user(user_id, user_role)
        critical_alerts = [
            n
            for n in unread
            if n.priority in (NotificationPriority.CRITICAL, NotificationPriority.HIGH)
        ]
        return critical_alerts[:limit], len(critical_alerts)

    async def get_by_id_for_user(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str | None = None,
    ) -> Notification | None:
        """Fetch a single notification visible to the user."""
        result = await self.session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                or_(
                    and_(
                        Notification.recipient_type == RecipientType.USER,
                        Notification.recipient_user_id == user_id,
                    ),
                    Notification.recipient_type == RecipientType.BROADCAST,
                    *(
                        [
                            and_(
                                Notification.recipient_type == RecipientType.ROLE,
                                Notification.recipient_role == user_role,
                            )
                        ]
                        if user_role
                        else []
                    ),
                ),
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    async def mark_read(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str | None = None,
    ) -> Notification | None:
        """Mark a single notification as read; returns updated record."""
        notification = await self.get_by_id_for_user(
            notification_id, user_id, user_role
        )
        if notification is None:
            return None
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(UTC)
            self.session.add(notification)
            await self.session.flush()
            await self.session.refresh(notification)
        return notification

    async def mark_all_read(
        self,
        user_id: uuid.UUID,
        user_role: str | None = None,
    ) -> int:
        """
        Mark all unread notifications for a user as read.

        Returns the number of rows updated.
        """
        unread = await self.get_unread_for_user(user_id, user_role)
        now = datetime.now(UTC)
        count = 0
        for n in unread:
            n.is_read = True
            n.read_at = now
            self.session.add(n)
            count += 1
        if count:
            await self.session.flush()
        return count

    async def delete_for_user(
        self,
        notification_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str | None = None,
    ) -> bool:
        """Delete a notification visible to the user. Returns True if deleted."""
        notification = await self.get_by_id_for_user(
            notification_id, user_id, user_role
        )
        if notification is None:
            return False
        await self.session.delete(notification)
        await self.session.flush()
        return True

    # ------------------------------------------------------------------
    # Admin helpers
    # ------------------------------------------------------------------

    async def get_all_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Notification], int]:
        """Return all notifications (admin view)."""
        count_result = await self.session.execute(
            select(func.count()).select_from(Notification)
        )
        total = count_result.scalar_one()
        result = await self.session.execute(
            select(Notification)
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total


# ---------------------------------------------------------------------------
# NotificationPreferenceRepository
# ---------------------------------------------------------------------------


class NotificationPreferenceRepository(BaseRepository[NotificationPreference]):
    """Queries for the ``notification_preferences`` table."""

    model = NotificationPreference

    async def get_for_user(
        self, user_id: uuid.UUID
    ) -> NotificationPreference | None:
        """Fetch preferences for a given user."""
        return await self.session.get(NotificationPreference, user_id)

    async def get_or_create(
        self, user_id: uuid.UUID
    ) -> NotificationPreference:
        """Return existing preferences or create defaults."""
        pref = await self.get_for_user(user_id)
        if pref is None:
            pref = NotificationPreference(user_id=user_id)
            self.session.add(pref)
            await self.session.flush()
            await self.session.refresh(pref)
        return pref

    async def upsert(
        self,
        user_id: uuid.UUID,
        **kwargs,
    ) -> NotificationPreference:
        """Create or update notification preferences."""
        pref = await self.get_or_create(user_id)
        for key, value in kwargs.items():
            if value is not None:
                setattr(pref, key, value)
        self.session.add(pref)
        await self.session.flush()
        await self.session.refresh(pref)
        return pref
