"""
Notification service — Phase 6A.

Handles:
  - Creating and persisting notifications
  - Delivering via WebSocket (personal / role / broadcast)
  - Delivering via email (respecting preferences)
  - Reading, marking read/unread, deleting
  - Notification preferences CRUD
  - Admin broadcast notifications
  - Automatic notifications triggered by application events
  - Dashboard widget data
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.notification import (
    Notification,
    NotificationPreference,
    NotificationPriority,
    NotificationType,
    RecipientType,
)
from app.models.user import User
from app.repositories.notification import (
    NotificationPreferenceRepository,
    NotificationRepository,
)
from app.repositories.user import UserRepository
from app.schemas.notification import (
    AdminNotificationSend,
    CriticalAlertsResponse,
    NotificationCreate,
    NotificationPreferenceUpdate,
    NotificationRead,
    NotificationSummary,
    RecentNotificationsResponse,
    UnreadCountResponse,
)
from app.websockets.events import EventType, make_event
from app.websockets.manager import ws_manager

logger = get_logger(__name__)


def _to_read(n: Notification) -> NotificationRead:
    return NotificationRead.model_validate(n)


def _to_summary(n: Notification) -> NotificationSummary:
    return NotificationSummary.model_validate(n)


def _get_user_role(user: User) -> str | None:
    """Return the name of the user's first role (for routing)."""
    if user.roles:
        return user.roles[0].name
    return None


class NotificationService:
    """
    Core notification business logic.

    All write methods create a DB record first and then attempt
    real-time delivery via WebSocket.  WebSocket failures are logged
    but never raise — notifications are durable via the DB.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._notifications = NotificationRepository(session)
        self._preferences = NotificationPreferenceRepository(session)
        self._users = UserRepository(session)

    # ------------------------------------------------------------------
    # Internal creation
    # ------------------------------------------------------------------

    async def _create_and_deliver(self, payload: NotificationCreate) -> Notification:
        """
        Persist a notification and deliver it via WebSocket.

        This is the single path through which all notifications flow.
        """
        notification = await self._notifications.create(
            title=payload.title,
            message=payload.message,
            type=payload.type,
            priority=payload.priority,
            recipient_type=payload.recipient_type,
            recipient_role=payload.recipient_role,
            recipient_user_id=payload.recipient_user_id,
            sender_id=payload.sender_id,
            data=payload.data,
        )

        event = make_event(
            EventType.NOTIFICATION_NEW,
            payload={"notification": _to_summary(notification).model_dump(mode="json")},
        )

        if payload.recipient_type == RecipientType.USER and payload.recipient_user_id:
            await ws_manager.publish_user_notification(
                str(payload.recipient_user_id), event
            )
        elif payload.recipient_type == RecipientType.ROLE and payload.recipient_role:
            await ws_manager.publish_role_notification(payload.recipient_role, event)
        elif payload.recipient_type == RecipientType.BROADCAST:
            await ws_manager.publish_broadcast(event)

        await self._maybe_send_email(notification, payload)
        return notification

    async def _maybe_send_email(
        self,
        notification: Notification,
        payload: NotificationCreate,
    ) -> None:
        """Send an email notification if the recipient has email enabled."""
        if payload.recipient_type != RecipientType.USER:
            return
        if not payload.recipient_user_id:
            return
        try:
            pref = await self._preferences.get_for_user(payload.recipient_user_id)
            if pref and not pref.enable_email:
                return
            if pref and pref.mute_until and pref.mute_until > datetime.now(UTC):
                return
            user = await self._users.get_by_id(payload.recipient_user_id)
            if user and user.email:
                from app.services.email import email_service

                await email_service.send_notification(
                    to_email=user.email,
                    full_name=f"{user.first_name} {user.last_name}",
                    title=payload.title,
                    message=payload.message,
                    notification_type=payload.type,
                    priority=payload.priority,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to send notification email",
                notification_id=str(notification.id),
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Public creation API
    # ------------------------------------------------------------------

    async def create_user_notification(
        self,
        *,
        recipient_user_id: uuid.UUID,
        title: str,
        message: str,
        type: NotificationType = NotificationType.INFO,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        sender_id: uuid.UUID | None = None,
        data: dict[str, Any] | None = None,
    ) -> Notification:
        """Create a notification for a specific user."""
        return await self._create_and_deliver(
            NotificationCreate(
                title=title,
                message=message,
                type=type,
                priority=priority,
                recipient_type=RecipientType.USER,
                recipient_user_id=recipient_user_id,
                sender_id=sender_id,
                data=data,
            )
        )

    async def create_role_notification(
        self,
        *,
        recipient_role: str,
        title: str,
        message: str,
        type: NotificationType = NotificationType.INFO,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        sender_id: uuid.UUID | None = None,
        data: dict[str, Any] | None = None,
    ) -> Notification:
        """Create a notification for all users with a specific role."""
        return await self._create_and_deliver(
            NotificationCreate(
                title=title,
                message=message,
                type=type,
                priority=priority,
                recipient_type=RecipientType.ROLE,
                recipient_role=recipient_role,
                sender_id=sender_id,
                data=data,
            )
        )

    async def create_broadcast_notification(
        self,
        *,
        title: str,
        message: str,
        type: NotificationType = NotificationType.INFO,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        sender_id: uuid.UUID | None = None,
        data: dict[str, Any] | None = None,
    ) -> Notification:
        """Create a broadcast notification for all users."""
        return await self._create_and_deliver(
            NotificationCreate(
                title=title,
                message=message,
                type=type,
                priority=priority,
                recipient_type=RecipientType.BROADCAST,
                sender_id=sender_id,
                data=data,
            )
        )

    # ------------------------------------------------------------------
    # Admin broadcast
    # ------------------------------------------------------------------

    async def admin_send(self, payload: AdminNotificationSend, *, actor: User) -> Notification:
        """Admin-triggered notification send."""
        if payload.recipient_user_id:
            return await self.create_user_notification(
                recipient_user_id=payload.recipient_user_id,
                title=payload.title,
                message=payload.message,
                type=payload.type,
                priority=payload.priority,
                sender_id=actor.id,
                data=payload.data,
            )
        elif payload.recipient_role:
            return await self.create_role_notification(
                recipient_role=payload.recipient_role,
                title=payload.title,
                message=payload.message,
                type=payload.type,
                priority=payload.priority,
                sender_id=actor.id,
                data=payload.data,
            )
        else:  # broadcast_all
            return await self.create_broadcast_notification(
                title=payload.title,
                message=payload.message,
                type=payload.type,
                priority=payload.priority,
                sender_id=actor.id,
                data=payload.data,
            )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def list_notifications(
        self,
        current_user: User,
        *,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[NotificationRead], int]:
        role = _get_user_role(current_user)
        offset = (page - 1) * size
        notifications, total = await self._notifications.get_for_user(
            current_user.id, role, offset=offset, limit=size
        )
        return [_to_read(n) for n in notifications], total

    async def list_unread(
        self,
        current_user: User,
        *,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[NotificationRead], int]:
        role = _get_user_role(current_user)
        offset = (page - 1) * size
        notifications, total = await self._notifications.get_for_user(
            current_user.id, role, offset=offset, limit=size, unread_only=True
        )
        return [_to_read(n) for n in notifications], total

    async def get_by_id(
        self,
        notification_id: uuid.UUID,
        current_user: User,
    ) -> NotificationRead:
        from app.core.exceptions import NotFoundError

        role = _get_user_role(current_user)
        notification = await self._notifications.get_by_id_for_user(
            notification_id, current_user.id, role
        )
        if not notification:
            raise NotFoundError("Notification not found.")
        return _to_read(notification)

    # ------------------------------------------------------------------
    # Mark read / delete
    # ------------------------------------------------------------------

    async def mark_read(
        self,
        notification_id: uuid.UUID,
        current_user: User,
    ) -> NotificationRead:
        from app.core.exceptions import NotFoundError

        role = _get_user_role(current_user)
        notification = await self._notifications.mark_read(
            notification_id, current_user.id, role
        )
        if not notification:
            raise NotFoundError("Notification not found.")

        event = make_event(
            EventType.NOTIFICATION_READ,
            payload={"notification_id": str(notification_id)},
        )
        await ws_manager.send_to_user(str(current_user.id), event)
        return _to_read(notification)

    async def mark_all_read(self, current_user: User) -> int:
        role = _get_user_role(current_user)
        count = await self._notifications.mark_all_read(current_user.id, role)
        if count:
            event = make_event(
                EventType.NOTIFICATION_ALL_READ,
                payload={"count": count},
            )
            await ws_manager.send_to_user(str(current_user.id), event)
        return count

    async def delete_notification(
        self,
        notification_id: uuid.UUID,
        current_user: User,
    ) -> None:
        from app.core.exceptions import NotFoundError

        role = _get_user_role(current_user)
        deleted = await self._notifications.delete_for_user(
            notification_id, current_user.id, role
        )
        if not deleted:
            raise NotFoundError("Notification not found.")

        event = make_event(
            EventType.NOTIFICATION_DELETED,
            payload={"notification_id": str(notification_id)},
        )
        await ws_manager.send_to_user(str(current_user.id), event)

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    async def get_preferences(self, user: User) -> NotificationPreference:
        return await self._preferences.get_or_create(user.id)

    async def update_preferences(
        self,
        user: User,
        update: NotificationPreferenceUpdate,
    ) -> NotificationPreference:
        kwargs = update.model_dump(exclude_none=True)
        return await self._preferences.upsert(user.id, **kwargs)

    # ------------------------------------------------------------------
    # Dashboard widgets
    # ------------------------------------------------------------------

    async def get_unread_count(self, current_user: User) -> UnreadCountResponse:
        role = _get_user_role(current_user)
        counts = await self._notifications.count_unread(current_user.id, role)
        return UnreadCountResponse(**counts)

    async def get_recent_notifications(
        self,
        current_user: User,
        limit: int = 10,
    ) -> RecentNotificationsResponse:
        role = _get_user_role(current_user)
        notifications = await self._notifications.get_recent_for_user(
            current_user.id, role, limit=limit
        )
        counts = await self._notifications.count_unread(current_user.id, role)
        return RecentNotificationsResponse(
            notifications=[_to_summary(n) for n in notifications],
            unread_count=counts["unread_count"],
        )

    async def get_critical_alerts(self, current_user: User) -> CriticalAlertsResponse:
        role = _get_user_role(current_user)
        alerts, total = await self._notifications.get_critical_alerts(
            current_user.id, role
        )
        return CriticalAlertsResponse(
            alerts=[_to_summary(a) for a in alerts],
            total=total,
        )


# ---------------------------------------------------------------------------
# Auto-notification helpers (called from other services)
# ---------------------------------------------------------------------------


class NotificationEventService:
    """
    Convenience wrapper for emitting auto-notifications from other services.

    All methods are fire-and-forget — they catch all exceptions internally
    so that notification failures never propagate to the calling service.

    Usage::

        notifier = NotificationEventService(db_session)
        await notifier.notify_po_created(po_number, po_id, actor)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._svc = NotificationService(session)

    # ---------- Authentication -------------------------------------------

    async def notify_user_registered(self, user: User) -> None:
        """Notify admins that a new user has registered."""
        try:
            await self._svc.create_role_notification(
                recipient_role="ADMIN",
                title="New User Registered",
                message=(
                    f"{user.first_name} {user.last_name} ({user.email}) "
                    "has created an account and is awaiting approval."
                ),
                type=NotificationType.USER,
                priority=NotificationPriority.NORMAL,
                data={"user_id": str(user.id), "email": user.email},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify user_registered failed", error=str(exc))

    async def notify_password_reset(self, user: User) -> None:
        """Notify the user their password was changed."""
        try:
            await self._svc.create_user_notification(
                recipient_user_id=user.id,
                title="Password Reset Successful",
                message="Your password has been reset successfully. If this wasn't you, contact support immediately.",
                type=NotificationType.SECURITY,
                priority=NotificationPriority.HIGH,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify password_reset failed", error=str(exc))

    async def notify_login_failure(self, user: User, attempts: int) -> None:
        """Notify the user of a failed login attempt."""
        try:
            await self._svc.create_user_notification(
                recipient_user_id=user.id,
                title="Failed Login Attempt",
                message=(
                    f"A failed login attempt was detected on your account "
                    f"({attempts} failed attempt(s)). If this wasn't you, "
                    "please change your password immediately."
                ),
                type=NotificationType.SECURITY,
                priority=NotificationPriority.HIGH,
                data={"failed_attempts": attempts},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify login_failure failed", error=str(exc))

    # ---------- Purchase Orders ------------------------------------------

    async def notify_po_created(
        self, po_number: str, po_id: uuid.UUID, actor: User
    ) -> None:
        try:
            await self._svc.create_role_notification(
                recipient_role="ADMIN",
                title="Purchase Order Created",
                message=(
                    f"Purchase Order {po_number} has been created "
                    f"by {actor.first_name} {actor.last_name}."
                ),
                type=NotificationType.PURCHASE_ORDER,
                priority=NotificationPriority.NORMAL,
                sender_id=actor.id,
                data={"po_id": str(po_id), "po_number": po_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify po_created failed", error=str(exc))

    async def notify_po_submitted(
        self, po_number: str, po_id: uuid.UUID, actor: User
    ) -> None:
        try:
            await self._svc.create_role_notification(
                recipient_role="ADMIN",
                title="Purchase Order Awaiting Approval",
                message=f"Purchase Order {po_number} has been submitted and is awaiting approval.",
                type=NotificationType.PURCHASE_ORDER,
                priority=NotificationPriority.HIGH,
                sender_id=actor.id,
                data={"po_id": str(po_id), "po_number": po_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify po_submitted failed", error=str(exc))

    async def notify_po_approved(
        self,
        po_number: str,
        po_id: uuid.UUID,
        actor: User,
        requester_id: uuid.UUID,
    ) -> None:
        try:
            await self._svc.create_user_notification(
                recipient_user_id=requester_id,
                title="Purchase Order Approved",
                message=f"Your Purchase Order {po_number} has been approved.",
                type=NotificationType.PURCHASE_ORDER,
                priority=NotificationPriority.NORMAL,
                sender_id=actor.id,
                data={"po_id": str(po_id), "po_number": po_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify po_approved failed", error=str(exc))

    async def notify_po_rejected(
        self,
        po_number: str,
        po_id: uuid.UUID,
        actor: User,
        requester_id: uuid.UUID,
        reason: str | None = None,
    ) -> None:
        try:
            msg = f"Your Purchase Order {po_number} has been rejected."
            if reason:
                msg += f" Reason: {reason}"
            await self._svc.create_user_notification(
                recipient_user_id=requester_id,
                title="Purchase Order Rejected",
                message=msg,
                type=NotificationType.PURCHASE_ORDER,
                priority=NotificationPriority.HIGH,
                sender_id=actor.id,
                data={"po_id": str(po_id), "po_number": po_number, "reason": reason},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify po_rejected failed", error=str(exc))

    async def notify_po_cancelled(
        self,
        po_number: str,
        po_id: uuid.UUID,
        actor: User,
        requester_id: uuid.UUID,
    ) -> None:
        try:
            await self._svc.create_user_notification(
                recipient_user_id=requester_id,
                title="Purchase Order Cancelled",
                message=f"Purchase Order {po_number} has been cancelled.",
                type=NotificationType.PURCHASE_ORDER,
                priority=NotificationPriority.NORMAL,
                sender_id=actor.id,
                data={"po_id": str(po_id), "po_number": po_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify po_cancelled failed", error=str(exc))

    # ---------- GRN -------------------------------------------------------

    async def notify_grn_created(
        self, grn_number: str, grn_id: uuid.UUID, actor: User
    ) -> None:
        try:
            await self._svc.create_role_notification(
                recipient_role="ADMIN",
                title="GRN Created",
                message=f"Goods Receipt Note {grn_number} has been created.",
                type=NotificationType.GRN,
                priority=NotificationPriority.NORMAL,
                sender_id=actor.id,
                data={"grn_id": str(grn_id), "grn_number": grn_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify grn_created failed", error=str(exc))

    async def notify_grn_approved(
        self, grn_number: str, grn_id: uuid.UUID, actor: User
    ) -> None:
        try:
            await self._svc.create_role_notification(
                recipient_role="STORE_KEEPER",
                title="GRN Approved — Stock Updated",
                message=(
                    f"Goods Receipt Note {grn_number} has been approved. "
                    "Inventory has been updated accordingly."
                ),
                type=NotificationType.GRN,
                priority=NotificationPriority.NORMAL,
                sender_id=actor.id,
                data={"grn_id": str(grn_id), "grn_number": grn_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify grn_approved failed", error=str(exc))

    async def notify_grn_cancelled(
        self, grn_number: str, grn_id: uuid.UUID, actor: User
    ) -> None:
        try:
            await self._svc.create_role_notification(
                recipient_role="ADMIN",
                title="GRN Cancelled",
                message=f"Goods Receipt Note {grn_number} has been cancelled.",
                type=NotificationType.GRN,
                priority=NotificationPriority.NORMAL,
                sender_id=actor.id,
                data={"grn_id": str(grn_id), "grn_number": grn_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify grn_cancelled failed", error=str(exc))

    # ---------- Inventory -------------------------------------------------

    async def notify_low_stock(
        self,
        product_name: str,
        product_id: uuid.UUID,
        current_qty: float,
        reorder_level: float,
    ) -> None:
        try:
            await self._svc.create_role_notification(
                recipient_role="STORE_KEEPER",
                title="Low Stock Alert",
                message=(
                    f"Product '{product_name}' is running low. "
                    f"Current stock: {current_qty:.2f} "
                    f"(reorder level: {reorder_level:.2f})."
                ),
                type=NotificationType.LOW_STOCK,
                priority=NotificationPriority.HIGH,
                data={
                    "product_id": str(product_id),
                    "product_name": product_name,
                    "current_qty": current_qty,
                    "reorder_level": reorder_level,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify low_stock failed", error=str(exc))

    async def notify_out_of_stock(
        self,
        product_name: str,
        product_id: uuid.UUID,
    ) -> None:
        try:
            await self._svc.create_role_notification(
                recipient_role="STORE_KEEPER",
                title="Out of Stock Alert",
                message=f"Product '{product_name}' is out of stock. Immediate replenishment required.",
                type=NotificationType.OUT_OF_STOCK,
                priority=NotificationPriority.CRITICAL,
                data={"product_id": str(product_id), "product_name": product_name},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify out_of_stock failed", error=str(exc))

    # ---------- Stock Releases --------------------------------------------

    async def notify_stock_release_created(
        self, release_number: str, release_id: uuid.UUID, actor: User
    ) -> None:
        try:
            await self._svc.create_role_notification(
                recipient_role="ADMIN",
                title="Stock Release Created",
                message=f"Stock Release {release_number} has been created by {actor.first_name} {actor.last_name}.",
                type=NotificationType.STOCK_RELEASE,
                priority=NotificationPriority.NORMAL,
                sender_id=actor.id,
                data={"release_id": str(release_id), "release_number": release_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify stock_release_created failed", error=str(exc))

    async def notify_stock_release_submitted(
        self, release_number: str, release_id: uuid.UUID, actor: User
    ) -> None:
        try:
            await self._svc.create_role_notification(
                recipient_role="ADMIN",
                title="Stock Release Pending Approval",
                message=f"Stock Release {release_number} has been submitted for approval.",
                type=NotificationType.STOCK_RELEASE,
                priority=NotificationPriority.HIGH,
                sender_id=actor.id,
                data={"release_id": str(release_id), "release_number": release_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify stock_release_submitted failed", error=str(exc))

    async def notify_stock_release_approved(
        self,
        release_number: str,
        release_id: uuid.UUID,
        actor: User,
        requester_id: uuid.UUID,
    ) -> None:
        try:
            await self._svc.create_user_notification(
                recipient_user_id=requester_id,
                title="Stock Release Approved",
                message=f"Your Stock Release {release_number} has been approved and inventory has been deducted.",
                type=NotificationType.STOCK_RELEASE,
                priority=NotificationPriority.NORMAL,
                sender_id=actor.id,
                data={"release_id": str(release_id), "release_number": release_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify stock_release_approved failed", error=str(exc))

    async def notify_stock_release_cancelled(
        self,
        release_number: str,
        release_id: uuid.UUID,
        actor: User,
        requester_id: uuid.UUID,
    ) -> None:
        try:
            await self._svc.create_user_notification(
                recipient_user_id=requester_id,
                title="Stock Release Cancelled",
                message=f"Stock Release {release_number} has been cancelled.",
                type=NotificationType.STOCK_RELEASE,
                priority=NotificationPriority.NORMAL,
                sender_id=actor.id,
                data={"release_id": str(release_id), "release_number": release_number},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify stock_release_cancelled failed", error=str(exc))

    # ---------- System events --------------------------------------------

    async def notify_system_error(self, title: str, message: str) -> None:
        """Broadcast a critical system error to all admins."""
        try:
            await self._svc.create_role_notification(
                recipient_role="ADMIN",
                title=title,
                message=message,
                type=NotificationType.ERROR,
                priority=NotificationPriority.CRITICAL,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify system_error failed", error=str(exc))

    async def notify_maintenance(
        self,
        message: str,
        sender_id: uuid.UUID | None = None,
    ) -> None:
        """Broadcast a scheduled maintenance notice to all users."""
        try:
            await self._svc.create_broadcast_notification(
                title="Scheduled Maintenance",
                message=message,
                type=NotificationType.SYSTEM,
                priority=NotificationPriority.HIGH,
                sender_id=sender_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-notify maintenance failed", error=str(exc))
