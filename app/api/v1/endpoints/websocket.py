"""
WebSocket endpoint — /api/v1/ws/connect

Demonstrates the connection manager and event system.
Clients send and receive JSON-encoded ``WebSocketEvent`` objects.

Protocol
--------
On connect:   server sends  ``system.connected`` with the connection_id.
Ping/pong:    client sends  ``{"event": "system.ping"}``
              server replies ``{"event": "system.pong"}``
On disconnect: server removes the connection from the registry.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.websockets.events import EventType, make_event
from app.websockets.manager import ws_manager

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/connect")
async def websocket_endpoint(websocket: WebSocket, room: str | None = None) -> None:
    """
    Connect to the WebSocket hub.

    Optional query parameter ``room`` places the connection in a named
    broadcast group.
    """
    connection_id = await ws_manager.connect(websocket, room=room)

    # Notify the client of their connection ID
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
                # Echo unknown events back (will be replaced by real handlers in Phase 1+)
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
