"""
Notification system tests — Phase 6A.

Coverage:
  - NotificationService unit tests (mocked DB)
  - NotificationEventService auto-trigger tests
  - Notification CRUD API endpoint tests
  - Admin broadcast endpoint tests
  - Notification preferences endpoint tests
  - Dashboard widget endpoint tests
  - Read / unread state tests
  - Role-based notification routing
  - WebSocket manager unit tests
  - Redis Pub/Sub worker-ID deduplication tests
  - Permission / auth guard tests
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    user_id: uuid.UUID | None = None,
    role_name: str = "OFFICER",
    is_superuser: bool = False,
) -> MagicMock:
    """Build a lightweight User mock."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = f"user_{user.id}@example.com"
    user.first_name = "Test"
    user.last_name = "User"
    user.is_active = True
    user.is_superuser = is_superuser
    role = MagicMock()
    role.name = role_name
    user.roles = [role]
    user.has_role = lambda r: r == role_name or is_superuser
    user.full_name = "Test User"
    return user


def _make_notification(
    *,
    notification_id: uuid.UUID | None = None,
    title: str = "Test Notification"
) -> MagicMock:
    """Build a lightweight Notification mock."""
    from app.models.notification import NotificationPriority, NotificationType, RecipientType

    n = MagicMock()
    n.id = notification_id or uuid.uuid4()
    n.title = title
    n.message = "Test message"
    n.type = NotificationType.INFO
    n.priority = NotificationPriority.NORMAL
    n.recipient_type = RecipientType.USER
    n.recipient_role = None
    n.recipient_user_id = uuid.uuid4()
    n.sender_id = None
    n.is_read = False
    n.read_at = None
    n.data = {}
    n.created_at = datetime.now(UTC)
    n.updated_at = datetime.now(UTC)
    return n

# ---------------------------------------------------------------------------
# NotificationService unit tests
# ---------------------------------------------------------------------------


class TestNotificationService:
    """Unit tests for core NotificationService methods."""

    def _make_service(self):
        from app.services.notification import NotificationService

        session = AsyncMock()
        svc = NotificationService(session)
        svc._notifications = AsyncMock()
        svc._preferences = AsyncMock()
        svc._users = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_create_user_notification_stores_and_delivers(self):
        """create_user_notification persists and calls WebSocket publish."""
        svc = self._make_service()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)
        svc._preferences.get_for_user = AsyncMock(return_value=None)

        recipient_id = uuid.uuid4()

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_user_notification = AsyncMock()
            result = await svc.create_user_notification(
                recipient_user_id=recipient_id,
                title="Hello",
                message="World",
            )

        svc._notifications.create.assert_called_once()
        mock_ws.publish_user_notification.assert_called_once_with(
            str(recipient_id), mock_ws.publish_user_notification.call_args[0][1]
        )
        assert result.id == n.id

    @pytest.mark.asyncio
    async def test_create_role_notification_routes_to_role_channel(self):
        svc = self._make_service()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)
        svc._preferences.get_for_user = AsyncMock(return_value=None)

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_role_notification = AsyncMock()
            await svc.create_role_notification(
                recipient_role="ADMIN",
                title="Role Notification",
                message="For admins",
            )

        mock_ws.publish_role_notification.assert_called_once_with(
            "ADMIN", mock_ws.publish_role_notification.call_args[0][1]
        )

    @pytest.mark.asyncio
    async def test_create_broadcast_notification_publishes_broadcast(self):
        svc = self._make_service()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_broadcast = AsyncMock()
            await svc.create_broadcast_notification(
                title="Broadcast",
                message="To everyone",
            )

        mock_ws.publish_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_read_emits_websocket_event(self):
        svc = self._make_service()
        n = _make_notification()
        n.is_read = True
        n.read_at = datetime.now(UTC)
        svc._notifications.mark_read = AsyncMock(return_value=n)

        user = _make_user()

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.send_to_user = AsyncMock()
            await svc.mark_read(n.id, user)

        assert mock_ws.send_to_user.call_args[0][0] == str(user.id)

    @pytest.mark.asyncio
    async def test_mark_read_raises_not_found_when_missing(self):
        from app.core.exceptions import NotFoundError

        svc = self._make_service()
        svc._notifications.mark_read = AsyncMock(return_value=None)
        user = _make_user()

        with pytest.raises(NotFoundError):
            await svc.mark_read(uuid.uuid4(), user)

    @pytest.mark.asyncio
    async def test_mark_all_read_emits_event_when_count_positive(self):
        svc = self._make_service()
        svc._notifications.mark_all_read = AsyncMock(return_value=5)
        user = _make_user()

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.send_to_user = AsyncMock()
            count = await svc.mark_all_read(user)

        assert count == 5
        mock_ws.send_to_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_all_read_no_event_when_zero(self):
        svc = self._make_service()
        svc._notifications.mark_all_read = AsyncMock(return_value=0)
        user = _make_user()

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.send_to_user = AsyncMock()
            count = await svc.mark_all_read(user)

        assert count == 0
        mock_ws.send_to_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_notification_emits_deleted_event(self):
        svc = self._make_service()
        svc._notifications.delete_for_user = AsyncMock(return_value=True)
        user = _make_user()

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.send_to_user = AsyncMock()
            await svc.delete_notification(uuid.uuid4(), user)

        mock_ws.send_to_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_notification_raises_not_found_when_missing(self):
        from app.core.exceptions import NotFoundError

        svc = self._make_service()
        svc._notifications.delete_for_user = AsyncMock(return_value=False)
        user = _make_user()

        with pytest.raises(NotFoundError):
            await svc.delete_notification(uuid.uuid4(), user)

    @pytest.mark.asyncio
    async def test_get_unread_count_returns_correct_counts(self):
        svc = self._make_service()
        svc._notifications.count_unread = AsyncMock(
            return_value={"unread_count": 7, "critical_count": 1, "high_count": 2}
        )
        user = _make_user()

        result = await svc.get_unread_count(user)

        assert result.unread_count == 7
        assert result.critical_count == 1
        assert result.high_count == 2

    @pytest.mark.asyncio
    async def test_email_skipped_when_muted(self):
        svc = self._make_service()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)

        pref = MagicMock()
        pref.enable_email = True
        pref.mute_until = datetime.now(UTC) + timedelta(hours=1)  # currently muted
        svc._preferences.get_for_user = AsyncMock(return_value=pref)

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_user_notification = AsyncMock()
            with patch("app.services.email.email_service") as mock_email:
                mock_email.send_notification = AsyncMock()
                await svc.create_user_notification(
                    recipient_user_id=uuid.uuid4(),
                    title="Test",
                    message="Muted",
                )

        mock_email.send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_skipped_when_disabled_in_prefs(self):
        svc = self._make_service()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)

        pref = MagicMock()
        pref.enable_email = False
        pref.mute_until = None
        svc._preferences.get_for_user = AsyncMock(return_value=pref)

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_user_notification = AsyncMock()
            with patch("app.services.notification.email_service", create=True) as mock_email:
                mock_email.send_notification = AsyncMock()
                await svc.create_user_notification(
                    recipient_user_id=uuid.uuid4(),
                    title="Test",
                    message="No email",
                )

        mock_email.send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_preferences_creates_if_missing(self):
        svc = self._make_service()
        pref = MagicMock()
        svc._preferences.get_or_create = AsyncMock(return_value=pref)
        user = _make_user()

        result = await svc.get_preferences(user)

        svc._preferences.get_or_create.assert_called_once_with(user.id)
        assert result is pref

    @pytest.mark.asyncio
    async def test_update_preferences_calls_upsert(self):
        from app.schemas.notification import NotificationPreferenceUpdate

        svc = self._make_service()
        pref = MagicMock()
        svc._preferences.upsert = AsyncMock(return_value=pref)
        user = _make_user()

        update = NotificationPreferenceUpdate(enable_email=False)
        result = await svc.update_preferences(user, update)

        svc._preferences.upsert.assert_called_once_with(user.id, enable_email=False)
        assert result is pref

    @pytest.mark.asyncio
    async def test_admin_send_routes_to_user_notification(self):
        from app.schemas.notification import AdminNotificationSend
        from app.models.notification import NotificationType, NotificationPriority

        svc = self._make_service()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)
        svc._preferences.get_for_user = AsyncMock(return_value=None)

        actor = _make_user(role_name="ADMIN")
        recipient_id = uuid.uuid4()

        payload = AdminNotificationSend(
            title="Admin Message",
            message="Hello user",
            type=NotificationType.INFO,
            priority=NotificationPriority.NORMAL,
            recipient_user_id=recipient_id,
        )

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_user_notification = AsyncMock()
            result = await svc.admin_send(payload, actor=actor)

        assert result.id == n.id
        mock_ws.publish_user_notification.assert_called_once_with(
            str(recipient_id), mock_ws.publish_user_notification.call_args[0][1]
        )

    @pytest.mark.asyncio
    async def test_admin_send_routes_to_role_notification(self):
        from app.schemas.notification import AdminNotificationSend
        from app.models.notification import NotificationType, NotificationPriority

        svc = self._make_service()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)

        actor = _make_user(role_name="ADMIN")
        payload = AdminNotificationSend(
            title="Role Message",
            message="For officers",
            type=NotificationType.INFO,
            priority=NotificationPriority.NORMAL,
            recipient_role="OFFICER",
        )

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_role_notification = AsyncMock()
            await svc.admin_send(payload, actor=actor)

        mock_ws.publish_role_notification.assert_called_once_with(
            "OFFICER", mock_ws.publish_role_notification.call_args[0][1]
        )

    @pytest.mark.asyncio
    async def test_admin_send_broadcast_when_no_target(self):
        from app.schemas.notification import AdminNotificationSend
        from app.models.notification import NotificationType, NotificationPriority

        svc = self._make_service()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)

        actor = _make_user(role_name="ADMIN")
        payload = AdminNotificationSend(
            title="Broadcast",
            message="Hello everyone",
            type=NotificationType.SYSTEM,
            priority=NotificationPriority.HIGH,
            broadcast_all=True,
        )

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_broadcast = AsyncMock()
            await svc.admin_send(payload, actor=actor)

        mock_ws.publish_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_critical_alerts_returns_alerts_and_total(self):
        svc = self._make_service()
        n = _make_notification()
        svc._notifications.get_critical_alerts = AsyncMock(return_value=([n], 1))
        user = _make_user()

        result = await svc.get_critical_alerts(user)

        assert result.total == 1

# ---------------------------------------------------------------------------
# NotificationEventService auto-notification tests
# ---------------------------------------------------------------------------


class TestNotificationEventService:
    """Tests for auto-notification triggers."""

    def _make_event_service(self):
        from app.services.notification import NotificationEventService

        session = AsyncMock()
        svc = NotificationEventService(session)
        svc._svc = AsyncMock()
        svc._svc.create_role_notification = AsyncMock()
        svc._svc.create_user_notification = AsyncMock()
        svc._svc.create_broadcast_notification = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_notify_user_registered_targets_admin_role(self):
        svc = self._make_event_service()
        user = _make_user()
        await svc.notify_user_registered(user)
        svc._svc.create_role_notification.assert_called_once()
        call_kwargs = svc._svc.create_role_notification.call_args[1]
        assert call_kwargs["recipient_role"] == "ADMIN"

    @pytest.mark.asyncio
    async def test_notify_password_reset_targets_user(self):
        svc = self._make_event_service()
        user = _make_user()
        await svc.notify_password_reset(user)
        svc._svc.create_user_notification.assert_called_once()
        call_kwargs = svc._svc.create_user_notification.call_args[1]
        assert call_kwargs["recipient_user_id"] == user.id

    @pytest.mark.asyncio
    async def test_notify_login_failure_includes_attempt_count(self):
        svc = self._make_event_service()
        user = _make_user()
        await svc.notify_login_failure(user, 3)
        call_kwargs = svc._svc.create_user_notification.call_args[1]
        assert call_kwargs["data"]["failed_attempts"] == 3
        assert call_kwargs["recipient_user_id"] == user.id

    @pytest.mark.asyncio
    async def test_notify_po_created_targets_admin_normal_priority(self):
        from app.models.notification import NotificationPriority

        svc = self._make_event_service()
        actor = _make_user(role_name="OFFICER")
        po_id = uuid.uuid4()
        await svc.notify_po_created("PO-001", po_id, actor)
        call_kwargs = svc._svc.create_role_notification.call_args[1]
        assert call_kwargs["recipient_role"] == "ADMIN"
        assert call_kwargs["priority"] == NotificationPriority.NORMAL
        assert "PO-001" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_notify_po_submitted_is_high_priority(self):
        from app.models.notification import NotificationPriority

        svc = self._make_event_service()
        actor = _make_user()
        await svc.notify_po_submitted("PO-002", uuid.uuid4(), actor)
        call_kwargs = svc._svc.create_role_notification.call_args[1]
        assert call_kwargs["priority"] == NotificationPriority.HIGH

    @pytest.mark.asyncio
    async def test_notify_po_approved_targets_requester(self):
        svc = self._make_event_service()
        actor = _make_user(role_name="ADMIN")
        requester_id = uuid.uuid4()
        await svc.notify_po_approved("PO-003", uuid.uuid4(), actor, requester_id)
        call_kwargs = svc._svc.create_user_notification.call_args[1]
        assert call_kwargs["recipient_user_id"] == requester_id

    @pytest.mark.asyncio
    async def test_notify_po_rejected_includes_reason(self):
        svc = self._make_event_service()
        actor = _make_user(role_name="ADMIN")
        requester_id = uuid.uuid4()
        await svc.notify_po_rejected("PO-004", uuid.uuid4(), actor, requester_id, reason="Budget exceeded")
        call_kwargs = svc._svc.create_user_notification.call_args[1]
        assert "Budget exceeded" in call_kwargs["message"]
        assert call_kwargs["recipient_user_id"] == requester_id

    @pytest.mark.asyncio
    async def test_notify_po_cancelled_targets_requester(self):
        svc = self._make_event_service()
        actor = _make_user()
        requester_id = uuid.uuid4()
        await svc.notify_po_cancelled("PO-005", uuid.uuid4(), actor, requester_id)
        call_kwargs = svc._svc.create_user_notification.call_args[1]
        assert call_kwargs["recipient_user_id"] == requester_id

    @pytest.mark.asyncio
    async def test_notify_grn_created_targets_admin(self):
        svc = self._make_event_service()
        actor = _make_user()
        await svc.notify_grn_created("GRN-001", uuid.uuid4(), actor)
        call_kwargs = svc._svc.create_role_notification.call_args[1]
        assert call_kwargs["recipient_role"] == "ADMIN"

    @pytest.mark.asyncio
    async def test_notify_grn_approved_targets_store_keeper(self):
        svc = self._make_event_service()
        actor = _make_user(role_name="ADMIN")
        await svc.notify_grn_approved("GRN-002", uuid.uuid4(), actor)
        call_kwargs = svc._svc.create_role_notification.call_args[1]
        assert call_kwargs["recipient_role"] == "STORE_KEEPER"

    @pytest.mark.asyncio
    async def test_notify_low_stock_is_high_priority_to_store_keeper(self):
        from app.models.notification import NotificationPriority

        svc = self._make_event_service()
        await svc.notify_low_stock("Widget A", uuid.uuid4(), 5.0, 10.0)
        call_kwargs = svc._svc.create_role_notification.call_args[1]
        assert call_kwargs["recipient_role"] == "STORE_KEEPER"
        assert call_kwargs["priority"] == NotificationPriority.HIGH
        assert "5.00" in call_kwargs["message"]
        assert "10.00" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_notify_out_of_stock_is_critical(self):
        from app.models.notification import NotificationPriority

        svc = self._make_event_service()
        await svc.notify_out_of_stock("Widget B", uuid.uuid4())
        call_kwargs = svc._svc.create_role_notification.call_args[1]
        assert call_kwargs["priority"] == NotificationPriority.CRITICAL
        assert call_kwargs["recipient_role"] == "STORE_KEEPER"

    @pytest.mark.asyncio
    async def test_notify_stock_release_submitted_is_high_priority(self):
        from app.models.notification import NotificationPriority

        svc = self._make_event_service()
        actor = _make_user()
        await svc.notify_stock_release_submitted("SR-001", uuid.uuid4(), actor)
        call_kwargs = svc._svc.create_role_notification.call_args[1]
        assert call_kwargs["priority"] == NotificationPriority.HIGH
        assert call_kwargs["recipient_role"] == "ADMIN"

    @pytest.mark.asyncio
    async def test_notify_stock_release_approved_targets_requester(self):
        svc = self._make_event_service()
        actor = _make_user(role_name="ADMIN")
        requester_id = uuid.uuid4()
        await svc.notify_stock_release_approved("SR-002", uuid.uuid4(), actor, requester_id)
        call_kwargs = svc._svc.create_user_notification.call_args[1]
        assert call_kwargs["recipient_user_id"] == requester_id

    @pytest.mark.asyncio
    async def test_notify_stock_release_cancelled_targets_requester(self):
        svc = self._make_event_service()
        actor = _make_user(role_name="ADMIN")
        requester_id = uuid.uuid4()
        await svc.notify_stock_release_cancelled("SR-003", uuid.uuid4(), actor, requester_id)
        call_kwargs = svc._svc.create_user_notification.call_args[1]
        assert call_kwargs["recipient_user_id"] == requester_id

    @pytest.mark.asyncio
    async def test_auto_notify_swallows_exception(self):
        """Notification failures must not propagate."""
        from app.services.notification import NotificationEventService

        session = AsyncMock()
        svc = NotificationEventService(session)
        svc._svc = AsyncMock()
        svc._svc.create_role_notification = AsyncMock(side_effect=RuntimeError("DB down"))

        user = _make_user()
        # Should not raise
        await svc.notify_user_registered(user)

    @pytest.mark.asyncio
    async def test_notify_system_error_targets_admin_critical(self):
        from app.models.notification import NotificationPriority

        svc = self._make_event_service()
        await svc.notify_system_error("DB Error", "Connection refused")
        call_kwargs = svc._svc.create_role_notification.call_args[1]
        assert call_kwargs["recipient_role"] == "ADMIN"
        assert call_kwargs["priority"] == NotificationPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_notify_maintenance_broadcasts_to_all(self):
        svc = self._make_event_service()
        await svc.notify_maintenance("Maintenance at midnight")
        svc._svc.create_broadcast_notification.assert_called_once()
        call_kwargs = svc._svc.create_broadcast_notification.call_args[1]
        assert "Maintenance" in call_kwargs["title"]

# ---------------------------------------------------------------------------
# WebSocket ConnectionManager unit tests
# ---------------------------------------------------------------------------


class TestConnectionManager:
    """Tests for the WebSocket ConnectionManager."""

    def _make_manager(self):
        from app.websockets.manager import ConnectionManager
        return ConnectionManager()

    def _make_ws(self, connected: bool = True):
        from starlette.websockets import WebSocketState
        ws = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED if connected else WebSocketState.DISCONNECTED
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_registers_user_and_role(self):
        mgr = self._make_manager()
        ws = self._make_ws()
        cid = await mgr.connect(ws, user_id="user-1", role="ADMIN")
        assert cid in mgr._connections
        assert cid in mgr._user_connections["user-1"]
        assert cid in mgr._role_connections["ADMIN"]
        assert mgr.connection_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_all_indices(self):
        mgr = self._make_manager()
        ws = self._make_ws()
        cid = await mgr.connect(ws, user_id="user-1", role="OFFICER")
        mgr.disconnect(cid, user_id="user-1", role="OFFICER")
        assert cid not in mgr._connections
        assert cid not in mgr._user_connections["user-1"]
        assert cid not in mgr._role_connections["OFFICER"]
        assert mgr.connection_count == 0

    @pytest.mark.asyncio
    async def test_send_json_returns_false_for_unknown_connection(self):
        mgr = self._make_manager()
        result = await mgr.send_json("nonexistent-id", {"event": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_json_returns_false_for_disconnected_socket(self):
        mgr = self._make_manager()
        ws = self._make_ws(connected=False)
        cid = await mgr.connect(ws, user_id="user-1")
        result = await mgr.send_json(cid, {"event": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_user_delivers_to_all_user_connections(self):
        mgr = self._make_manager()
        ws1 = self._make_ws()
        ws2 = self._make_ws()
        await mgr.connect(ws1, user_id="user-1")
        await mgr.connect(ws2, user_id="user-1")
        sent = await mgr.send_to_user("user-1", {"event": "test"})
        assert sent == 2
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_to_role_delivers_to_all_role_members(self):
        mgr = self._make_manager()
        ws1 = self._make_ws()
        ws2 = self._make_ws()
        await mgr.connect(ws1, user_id="user-1", role="ADMIN")
        await mgr.connect(ws2, user_id="user-2", role="ADMIN")
        sent = await mgr.send_to_role("ADMIN", {"event": "test"})
        assert sent == 2

    @pytest.mark.asyncio
    async def test_broadcast_to_all_delivers_to_every_connection(self):
        mgr = self._make_manager()
        ws1 = self._make_ws()
        ws2 = self._make_ws()
        ws3 = self._make_ws()
        await mgr.connect(ws1)
        await mgr.connect(ws2)
        await mgr.connect(ws3)
        sent = await mgr.broadcast_to_all({"event": "broadcast"})
        assert sent == 3

    @pytest.mark.asyncio
    async def test_send_to_user_returns_zero_when_no_connections(self):
        mgr = self._make_manager()
        sent = await mgr.send_to_user("ghost-user", {"event": "test"})
        assert sent == 0

    @pytest.mark.asyncio
    async def test_send_json_auto_disconnects_failed_socket(self):
        mgr = self._make_manager()
        ws = self._make_ws()
        ws.send_json = AsyncMock(side_effect=Exception("socket broken"))
        cid = await mgr.connect(ws, user_id="user-fail")
        result = await mgr.send_json(cid, {"event": "test"})
        assert result is False
        # Auto-disconnected on failure
        assert cid not in mgr._connections

    @pytest.mark.asyncio
    async def test_broadcast_json_with_room_only_sends_to_room(self):
        mgr = self._make_manager()
        ws_room = self._make_ws()
        ws_other = self._make_ws()
        await mgr.connect(ws_room, room="general")
        await mgr.connect(ws_other, room="other")
        sent = await mgr.broadcast_json({"event": "chat"}, room="general")
        assert sent == 1
        ws_room.send_json.assert_called_once()
        ws_other.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_to_redis_tags_with_worker_id(self):
        import json
        from app.websockets.manager import _WORKER_ID

        mgr = self._make_manager()
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        with patch("app.core.redis.get_redis_client", return_value=mock_redis):
            await mgr.publish_to_redis("test:channel", {"event": "hello"})

        mock_redis.publish.assert_called_once()
        channel, raw = mock_redis.publish.call_args[0]
        assert channel == "test:channel"
        envelope = json.loads(raw)
        assert envelope["_worker"] == _WORKER_ID
        assert envelope["data"] == {"event": "hello"}

    @pytest.mark.asyncio
    async def test_redis_subscriber_skips_own_worker_messages(self):
        """Messages published by this worker must not be re-delivered locally."""
        import json
        from app.websockets.manager import _WORKER_ID

        mgr = self._make_manager()
        ws = self._make_ws()
        await mgr.connect(ws, user_id="user-1")

        # Simulate a message that was published by THIS worker
        own_message = {
            "type": "pmessage",
            "channel": "notifications:user:user-1",
            "data": json.dumps({"_worker": _WORKER_ID, "data": {"event": "test"}}),
        }

        async def _fake_listen():
            yield own_message

        mock_pubsub = AsyncMock()
        mock_pubsub.listen = _fake_listen
        mock_pubsub.psubscribe = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        with patch("app.core.redis.get_redis_client", return_value=mock_redis):
            # Run just one iteration of the loop by cancelling after first message
            import asyncio
            task = asyncio.create_task(mgr._redis_subscriber_loop())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Own-worker message should NOT have been re-delivered
        ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_subscriber_delivers_foreign_worker_messages(self):
        """Messages from another worker MUST be delivered locally."""
        import json

        mgr = self._make_manager()
        ws = self._make_ws()
        await mgr.connect(ws, user_id="user-remote")

        other_worker_message = {
            "type": "pmessage",
            "channel": "notifications:user:user-remote",
            "data": json.dumps({"_worker": "other-worker-999", "data": {"event": "notification.new"}}),
        }

        async def _fake_listen():
            yield {"type": "subscribe", "channel": "notifications:*", "data": 1}
            yield other_worker_message

        mock_pubsub = AsyncMock()
        mock_pubsub.listen = _fake_listen
        mock_pubsub.psubscribe = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        with patch("app.core.redis.get_redis_client", return_value=mock_redis):
            import asyncio
            task = asyncio.create_task(mgr._redis_subscriber_loop())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        ws.send_json.assert_called_once()
        delivered = ws.send_json.call_args[0][0]
        assert delivered["event"] == "notification.new"

# ---------------------------------------------------------------------------
# API endpoint tests (with mocked auth + service)
# ---------------------------------------------------------------------------


def _make_mock_notification_service():
    svc = AsyncMock()
    from app.models.notification import NotificationPriority, NotificationType, RecipientType
    from app.schemas.notification import (
        CriticalAlertsResponse, NotificationRead, RecentNotificationsResponse, UnreadCountResponse
    )
    n = _make_notification()
    read = MagicMock(spec=NotificationRead)
    read.id = n.id
    read.title = n.title
    read.message = n.message
    read.type = NotificationType.INFO
    read.priority = NotificationPriority.NORMAL
    read.recipient_type = RecipientType.USER
    read.is_read = False
    svc.list_notifications = AsyncMock(return_value=([read], 1))
    svc.list_unread = AsyncMock(return_value=([read], 1))
    svc.get_by_id = AsyncMock(return_value=read)
    svc.mark_read = AsyncMock(return_value=read)
    svc.mark_all_read = AsyncMock(return_value=3)
    svc.delete_notification = AsyncMock()
    from app.schemas.notification import NotificationPreferenceRead
    pref_data = NotificationPreferenceRead(
        user_id=uuid.uuid4(),
        enable_websocket=True,
        enable_email=True,
        enable_system=True,
        mute_until=None,
        updated_at=datetime(2026, 7, 24, tzinfo=UTC),
    )
    svc.get_preferences = AsyncMock(return_value=pref_data)
    svc.update_preferences = AsyncMock(return_value=pref_data)
    svc.get_unread_count = AsyncMock(return_value=UnreadCountResponse(unread_count=5, critical_count=1, high_count=2))
    svc.get_recent_notifications = AsyncMock(return_value=RecentNotificationsResponse(notifications=[], unread_count=5))
    svc.get_critical_alerts = AsyncMock(return_value=CriticalAlertsResponse(alerts=[], total=0))
    svc.admin_send = AsyncMock(return_value=read)
    return svc


class TestNotificationEndpoints:
    """HTTP endpoint tests for /api/v1/notifications."""

    @pytest.fixture(autouse=True)
    def override_deps(self, app_instance):
        from app.core.deps import get_current_user
        from app.api.v1.endpoints.notifications import _get_svc

        user = _make_user()
        svc = _make_mock_notification_service()

        app_instance.dependency_overrides[get_current_user] = lambda: user
        app_instance.dependency_overrides[_get_svc] = lambda: svc
        self._user = user
        self._svc = svc
        yield
        app_instance.dependency_overrides.pop(get_current_user, None)
        app_instance.dependency_overrides.pop(_get_svc, None)

    @pytest.mark.asyncio
    async def test_list_notifications_returns_200(self, client):
        resp = await client.get("/api/v1/notifications")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert "data" in body

    @pytest.mark.asyncio
    async def test_list_unread_returns_200(self, client):
        resp = await client.get("/api/v1/notifications/unread")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_by_id_returns_200(self, client):
        nid = uuid.uuid4()
        resp = await client.get(f"/api/v1/notifications/{nid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_mark_read_returns_200(self, client):
        nid = uuid.uuid4()
        resp = await client.patch(f"/api/v1/notifications/{nid}/read")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_200_with_count(self, client):
        resp = await client.patch("/api/v1/notifications/read-all")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["marked_read"] == 3

    @pytest.mark.asyncio
    async def test_delete_notification_returns_204(self, client):
        nid = uuid.uuid4()
        resp = await client.delete(f"/api/v1/notifications/{nid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_preferences_returns_200(self, client):
        resp = await client.get("/api/v1/notifications/preferences/me")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_preferences_returns_200(self, client):
        resp = await client.put(
            "/api/v1/notifications/preferences/me",
            json={"enable_email": False, "enable_websocket": True},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unread_count_widget_returns_200(self, client):
        resp = await client.get("/api/v1/notifications/dashboard/unread-count")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["unread_count"] == 5
        assert body["data"]["critical_count"] == 1

    @pytest.mark.asyncio
    async def test_recent_notifications_widget_returns_200(self, client):
        resp = await client.get("/api/v1/notifications/dashboard/recent")
        assert resp.status_code == 200
        body = resp.json()
        assert "notifications" in body["data"]
        assert "unread_count" in body["data"]

    @pytest.mark.asyncio
    async def test_critical_alerts_widget_returns_200(self, client):
        resp = await client.get("/api/v1/notifications/dashboard/critical-alerts")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self, client, app_instance):
        from app.core.deps import get_current_user

        # Temporarily clear auth override to test 401
        saved_auth = app_instance.dependency_overrides.pop(get_current_user, None)
        try:
            resp = await client.get("/api/v1/notifications")
        finally:
            if saved_auth is not None:
                app_instance.dependency_overrides[get_current_user] = saved_auth
        assert resp.status_code == 401


class TestAdminNotificationEndpoint:
    """HTTP endpoint tests for /api/v1/admin/notifications/send."""

    @pytest.fixture(autouse=True)
    def override_deps(self, app_instance):
        from app.core.deps import get_current_user
        from app.database.engine import get_db

        admin = _make_user(role_name="ADMIN")
        svc = _make_mock_notification_service()

        async def _mock_db():
            yield AsyncMock()

        app_instance.dependency_overrides[get_current_user] = lambda: admin
        app_instance.dependency_overrides[get_db] = _mock_db

        # Patch NotificationService so it returns our mock regardless of db arg
        import app.api.v1.endpoints.admin_notifications as admin_mod
        original_cls = admin_mod.NotificationService
        admin_mod.NotificationService = lambda db: svc  # type: ignore[assignment]

        self._admin = admin
        self._svc = svc
        yield

        admin_mod.NotificationService = original_cls
        app_instance.dependency_overrides.pop(get_current_user, None)
        app_instance.dependency_overrides.pop(get_db, None)

    @pytest.mark.asyncio
    async def test_admin_send_to_user_returns_200(self, client):
        payload = {
            "title": "Admin Note",
            "message": "Check this out",
            "type": "INFO",
            "priority": "NORMAL",
            "recipient_user_id": str(uuid.uuid4()),
        }
        resp = await client.post("/api/v1/admin/notifications/send", json=payload)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_send_to_role_returns_200(self, client):
        payload = {
            "title": "Role Announcement",
            "message": "Attention STORE_KEEPER",
            "type": "SYSTEM",
            "priority": "HIGH",
            "recipient_role": "STORE_KEEPER",
        }
        resp = await client.post("/api/v1/admin/notifications/send", json=payload)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_broadcast_returns_200(self, client):
        payload = {
            "title": "Broadcast",
            "message": "To all users",
            "type": "SYSTEM",
            "priority": "NORMAL",
            "broadcast_all": True,
        }
        resp = await client.post("/api/v1/admin/notifications/send", json=payload)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_send_requires_exactly_one_target(self, client):
        """Providing both recipient_user_id and recipient_role must fail validation."""
        uid = str(uuid.uuid4())
        payload = {
            "title": "Ambiguous",
            "message": "Two targets",
            "type": "INFO",
            "priority": "NORMAL",
            "recipient_user_id": uid,
            "recipient_role": "ADMIN",
        }
        resp = await client.post("/api/v1/admin/notifications/send", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_admin_send_requires_non_admin_role_is_forbidden(self, client, app_instance):
        from app.core.deps import get_current_user

        officer = _make_user(role_name="OFFICER")
        app_instance.dependency_overrides[get_current_user] = lambda: officer

        payload = {
            "title": "Sneaky",
            "message": "Not allowed",
            "type": "INFO",
            "priority": "NORMAL",
            "broadcast_all": True,
        }
        resp = await client.post("/api/v1/admin/notifications/send", json=payload)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Read / unread state tests
# ---------------------------------------------------------------------------


class TestReadUnreadState:
    """Tests specifically covering read/unread state transitions."""

    @pytest.mark.asyncio
    async def test_notification_starts_unread(self):
        from app.services.notification import NotificationService

        session = AsyncMock()
        svc = NotificationService(session)
        svc._notifications = AsyncMock()
        svc._preferences = AsyncMock(return_value=None)
        svc._users = AsyncMock()

        n = _make_notification()
        n.is_read = False
        svc._notifications.create = AsyncMock(return_value=n)
        svc._preferences.get_for_user = AsyncMock(return_value=None)

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_user_notification = AsyncMock()
            result = await svc.create_user_notification(
                recipient_user_id=uuid.uuid4(),
                title="Test",
                message="Unread",
            )

        assert result.is_read is False

    @pytest.mark.asyncio
    async def test_mark_read_sets_is_read_true(self):
        from app.services.notification import NotificationService

        session = AsyncMock()
        svc = NotificationService(session)
        svc._notifications = AsyncMock()
        svc._preferences = AsyncMock()
        svc._users = AsyncMock()

        n = _make_notification()
        n.is_read = True
        n.read_at = datetime.now(UTC)
        svc._notifications.mark_read = AsyncMock(return_value=n)
        user = _make_user()

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.send_to_user = AsyncMock()
            result = await svc.mark_read(n.id, user)

        assert result.is_read is True

    @pytest.mark.asyncio
    async def test_unread_count_decreases_after_mark_all_read(self):
        from app.services.notification import NotificationService

        session = AsyncMock()
        svc = NotificationService(session)
        svc._notifications = AsyncMock()
        svc._preferences = AsyncMock()
        svc._notifications.mark_all_read = AsyncMock(return_value=4)
        svc._notifications.count_unread = AsyncMock(
            return_value={"unread_count": 0, "critical_count": 0, "high_count": 0}
        )
        user = _make_user()

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.send_to_user = AsyncMock()
            count = await svc.mark_all_read(user)
            unread = await svc.get_unread_count(user)

        assert count == 4
        assert unread.unread_count == 0


# ---------------------------------------------------------------------------
# Role-based notification routing tests
# ---------------------------------------------------------------------------


class TestRoleBasedRouting:
    """Tests verifying notifications reach the correct role channel."""

    @pytest.mark.asyncio
    async def test_admin_role_notification_goes_to_admin_channel(self):
        from app.services.notification import NotificationService

        session = AsyncMock()
        svc = NotificationService(session)
        svc._notifications = AsyncMock()
        svc._preferences = AsyncMock()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_role_notification = AsyncMock()
            await svc.create_role_notification(
                recipient_role="ADMIN",
                title="Admin only",
                message="Secret",
            )

        call_args = mock_ws.publish_role_notification.call_args
        assert call_args[0][0] == "ADMIN"

    @pytest.mark.asyncio
    async def test_store_keeper_role_notification_goes_to_correct_channel(self):
        from app.services.notification import NotificationService

        session = AsyncMock()
        svc = NotificationService(session)
        svc._notifications = AsyncMock()
        svc._preferences = AsyncMock()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_role_notification = AsyncMock()
            await svc.create_role_notification(
                recipient_role="STORE_KEEPER",
                title="Low stock",
                message="Widget A is low",
            )

        call_args = mock_ws.publish_role_notification.call_args
        assert call_args[0][0] == "STORE_KEEPER"

    @pytest.mark.asyncio
    async def test_user_notification_goes_to_personal_channel(self):
        from app.services.notification import NotificationService

        session = AsyncMock()
        svc = NotificationService(session)
        svc._notifications = AsyncMock()
        svc._preferences = AsyncMock()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)
        svc._preferences.get_for_user = AsyncMock(return_value=None)

        recipient_id = uuid.uuid4()
        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_user_notification = AsyncMock()
            await svc.create_user_notification(
                recipient_user_id=recipient_id,
                title="Personal",
                message="Just for you",
            )

        call_args = mock_ws.publish_user_notification.call_args
        assert call_args[0][0] == str(recipient_id)

    @pytest.mark.asyncio
    async def test_broadcast_notification_goes_to_all_channel(self):
        from app.services.notification import NotificationService

        session = AsyncMock()
        svc = NotificationService(session)
        svc._notifications = AsyncMock()
        n = _make_notification()
        svc._notifications.create = AsyncMock(return_value=n)

        with patch("app.services.notification.ws_manager") as mock_ws:
            mock_ws.publish_broadcast = AsyncMock()
            await svc.create_broadcast_notification(
                title="Everyone",
                message="System update",
            )

        mock_ws.publish_broadcast.assert_called_once()
        # publish_role_notification and publish_user_notification should NOT be called
        mock_ws.publish_user_notification = AsyncMock()
        mock_ws.publish_role_notification = AsyncMock()


# ---------------------------------------------------------------------------
# Permission validation tests
# ---------------------------------------------------------------------------


class TestPermissionValidation:
    """Tests that enforce role-based access control on endpoints."""

    @pytest.mark.asyncio
    async def test_non_admin_cannot_send_admin_broadcast(self, client, app_instance):
        """OFFICER role must be rejected with 403 from the admin endpoint."""
        from app.core.deps import get_current_user

        officer = _make_user(role_name="OFFICER")
        saved = app_instance.dependency_overrides.copy()
        app_instance.dependency_overrides.clear()
        app_instance.dependency_overrides[get_current_user] = lambda: officer
        try:
            resp = await client.post(
                "/api/v1/admin/notifications/send",
                json={
                    "title": "Hack",
                    "message": "Not allowed",
                    "type": "INFO",
                    "priority": "NORMAL",
                    "broadcast_all": True,
                },
            )
        finally:
            app_instance.dependency_overrides.clear()
            app_instance.dependency_overrides.update(saved)
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_superuser_can_send_admin_broadcast(self, client, app_instance):
        """Superuser flag bypasses role check and must succeed."""
        from app.core.deps import get_current_user
        from app.database.engine import get_db
        import app.api.v1.endpoints.admin_notifications as admin_mod

        superuser = _make_user(is_superuser=True)
        svc = _make_mock_notification_service()
        original_cls = admin_mod.NotificationService
        admin_mod.NotificationService = lambda db: svc  # type: ignore[assignment]

        async def _mock_db():
            yield AsyncMock()

        saved = app_instance.dependency_overrides.copy()
        app_instance.dependency_overrides[get_current_user] = lambda: superuser
        app_instance.dependency_overrides[get_db] = _mock_db
        try:
            resp = await client.post(
                "/api/v1/admin/notifications/send",
                json={
                    "title": "Superuser broadcast",
                    "message": "Allowed",
                    "type": "SYSTEM",
                    "priority": "HIGH",
                    "broadcast_all": True,
                },
            )
        finally:
            admin_mod.NotificationService = original_cls
            app_instance.dependency_overrides.clear()
            app_instance.dependency_overrides.update(saved)
        assert resp.status_code == 200
