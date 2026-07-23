"""
WebSocket endpoint — /api/v1/ws/connect and /api/v1/ws/notifications

Phase 6A: Enhanced with authenticated personal / role channels.

Protocols
---------
Generic endpoint:
  /ws/connect?room=<room>          — unauthenticated room-based channel

Notification endpoint:
  /ws/notifications?token=<jwt>    — authenticated personal + role channel

On connect:  server sends  ``system.connected`` with the connection_id.
Ping/pong:   client sends  ``{"event": "system.ping"}``
             server replies ``{"event": "system.pong"}``
Reconnect:   clients should reconnect with exponential back-off.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError

from app.core.logging import get_logger
from app.core.security import decode_token
from app.websockets.events import EventType, make_event
from app.websockets.manager import ws_manager

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Generic WebSocket (legacy / generic rooms)
# ---------------------------------------------------------------------------


@router.websocket("/connect")
async def websocket_endpoint(websocket: WebSocket, room: str | None = None) -> None:
    """
    Connect to the WebSocket hub.

    Optional query parameter ``room`` places the connection in a named
    broadcast group.
    """
    connection_id = await ws_manager.connect(websocket, room=room)

    await ws_manager.send_json(
        connection_id,
        make_event(
            EventType.CONNECTED,
            payload={"connection_id": connection_id, "room": room},
        ),
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws_manager.send_json(
                    connection_id,
                    make_event(
                        EventType.ERROR,
                        payload={"message": "Invalid JSON payload"},
                        sender=connection_id,
                    ),
                )
                continue

            event_type = data.get("event", "")

            if event_type == EventType.PING:
                await ws_manager.send_json(
                    connection_id,
                    make_event(EventType.PONG, sender=connection_id),
                )
            else:
                await ws_manager.send_json(
                    connection_id,
                    make_event(
                        EventType.ERROR,
                        payload={"message": f"Unknown event type: {event_type!r}"},
                        sender=connection_id,
                    ),
                )

    except WebSocketDisconnect:
        ws_manager.disconnect(connection_id)


# ---------------------------------------------------------------------------
# Notification WebSocket (authenticated — personal + role channels)
# ---------------------------------------------------------------------------


@router.websocket("/notifications")
async def notification_websocket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """
    Authenticated WebSocket for real-time notification delivery.

    Authentication is via a JWT access token passed as the ``token``
    query parameter (Bearer tokens cannot be sent in WS upgrade headers
    in most browser implementations).

    On successful connection the client is subscribed to:
      - Personal channel   (notifications:user:<user_id>)
      - Role channel       (notifications:role:<role_name>)
      - Broadcast channel  (notifications:broadcast)

    The server immediately sends the current unread count on connect.
    """
    # ------------------------------------------------------------------
    # Authenticate
    # ------------------------------------------------------------------
    user_id: str | None = None
    user_role: str | None = None
    auth_error: str | None = None

    if token:
        try:
            claims = decode_token(token)
            if claims.get("type") != "access":
                auth_error = "Token is not an access token."
            else:
                user_id = claims.get("sub")
        except JWTError:
            auth_error = "Invalid or expired token."
    else:
        auth_error = "Authentication token required."

    if auth_error or not user_id:
        # Accept then immediately close with an error message
        await websocket.accept()
        await websocket.send_json(
            make_event(
                EventType.ERROR,
                payload={"message": auth_error or "Authentication failed."},
            )
        )
        await websocket.close(code=4001)
        return

    # ------------------------------------------------------------------
    # Resolve user role from DB for role-channel subscription
    # ------------------------------------------------------------------
    try:
        from app.database.engine import get_session_factory
        from app.repositories.user import UserRepository
        import uuid as _uuid

        async with get_session_factory()() as db:
            users_repo = UserRepository(db)
            user = await users_repo.get_by_id_with_roles(_uuid.UUID(user_id))
            if user and user.roles:
                user_role = user.roles[0].name
    except Exception as exc:  # noqa: BLE001
        logger.warning("WS: could not resolve user role", user_id=user_id, error=str(exc))

    # ------------------------------------------------------------------
    # Connect to the manager with identity context
    # ------------------------------------------------------------------
    connection_id = await ws_manager.connect(
        websocket,
        user_id=user_id,
        role=user_role,
    )

    # Send connection confirmation
    await ws_manager.send_json(
        connection_id,
        make_event(
            EventType.CONNECTED,
            payload={
                "connection_id": connection_id,
                "user_id": user_id,
                "role": user_role,
                "channels": [
                    f"notifications:user:{user_id}",
                    *(
                        [f"notifications:role:{user_role}"]
                        if user_role
                        else []
                    ),
                    "notifications:broadcast",
                ],
            },
        ),
    )

    # Send current unread count immediately
    try:
        from app.database.engine import get_session_factory
        from app.services.notification import NotificationService
        from app.models.user import User as UserModel
        import uuid as _uuid

        async with get_session_factory()() as db:
            svc = NotificationService(db)
            # Build a minimal user object for the service call
            from app.repositories.user import UserRepository

            users_repo = UserRepository(db)
            db_user = await users_repo.get_by_id_with_roles(_uuid.UUID(user_id))
            if db_user:
                counts = await svc.get_unread_count(db_user)
                await ws_manager.send_json(
                    connection_id,
                    make_event(
                        EventType.NOTIFICATION_UNREAD_COUNT,
                        payload=counts.model_dump(),
                    ),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "WS: could not send initial unread count",
            user_id=user_id,
            error=str(exc),
        )

    # ------------------------------------------------------------------
    # Message loop
    # ------------------------------------------------------------------
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws_manager.send_json(
                    connection_id,
                    make_event(
                        EventType.ERROR,
                        payload={"message": "Invalid JSON payload"},
                    ),
                )
                continue

            event_type = data.get("event", "")

            if event_type == EventType.PING:
                await ws_manager.send_json(
                    connection_id,
                    make_event(EventType.PONG, sender=connection_id),
                )
            elif event_type == EventType.NOTIFICATION_UNREAD_COUNT:
                # Client requesting a fresh unread count
                try:
                    from app.database.engine import get_session_factory
                    from app.services.notification import NotificationService
                    from app.repositories.user import UserRepository
                    import uuid as _uuid

                    async with get_session_factory()() as db:
                        users_repo = UserRepository(db)
                        db_user = await users_repo.get_by_id_with_roles(_uuid.UUID(user_id))
                        if db_user:
                            svc = NotificationService(db)
                            counts = await svc.get_unread_count(db_user)
                            await ws_manager.send_json(
                                connection_id,
                                make_event(
                                    EventType.NOTIFICATION_UNREAD_COUNT,
                                    payload=counts.model_dump(),
                                ),
                            )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "WS: unread count refresh failed",
                        user_id=user_id,
                        error=str(exc),
                    )
            else:
                await ws_manager.send_json(
                    connection_id,
                    make_event(
                        EventType.ERROR,
                        payload={"message": f"Unknown event: {event_type!r}"},
                    ),
                )

    except WebSocketDisconnect:
        ws_manager.disconnect(connection_id, user_id=user_id, role=user_role)
        logger.info("Notification WS disconnected", user_id=user_id)
