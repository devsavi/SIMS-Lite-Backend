"""
WebSocket connection manager.

Tracks all active WebSocket connections and provides broadcast /
targeted send capabilities.  Redis pub/sub integration is stubbed
and ready for Phase 1 horizontal-scaling work.

Architecture overview
---------------------
- Each connection is identified by a unique ``connection_id`` (UUID).
- Connections can optionally be associated with a ``room`` (channel)
  for targeted group broadcasts.
- The manager is a singleton; import ``ws_manager`` for use in routes.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """
    In-process WebSocket connection registry.

    Thread-safety note: asyncio is single-threaded per event loop so
    the plain dict/set operations here are safe without locks.  If you
    run multiple workers you **must** add a Redis pub/sub bridge.
    """

    def __init__(self) -> None:
        # connection_id -> WebSocket
        self._connections: dict[str, WebSocket] = {}
        # room_name -> set of connection_ids
        self._rooms: dict[str, set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        websocket: WebSocket,
        room: str | None = None,
    ) -> str:
        """
        Accept the WebSocket upgrade and register the connection.

        Returns:
            A unique connection ID for this socket.
        """
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        self._connections[connection_id] = websocket
        if room:
            self._rooms[room].add(connection_id)
        logger.info(
            "WebSocket connected",
            connection_id=connection_id,
            room=room,
            total=len(self._connections),
        )
        return connection_id

    def disconnect(self, connection_id: str) -> None:
        """Deregister a connection (does not close the socket)."""
        self._connections.pop(connection_id, None)
        # Remove from all rooms
        for members in self._rooms.values():
            members.discard(connection_id)
        logger.info(
            "WebSocket disconnected",
            connection_id=connection_id,
            total=len(self._connections),
        )

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    async def send_json(self, connection_id: str, data: Any) -> bool:
        """
        Send a JSON-serialisable payload to a single connection.

        Returns:
            True if the message was sent, False if the connection is gone.
        """
        ws = self._connections.get(connection_id)
        if ws is None or ws.client_state != WebSocketState.CONNECTED:
            return False
        try:
            await ws.send_json(data)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "WebSocket send failed",
                connection_id=connection_id,
                error=str(exc),
            )
            self.disconnect(connection_id)
            return False

    async def broadcast_json(self, data: Any, room: str | None = None) -> int:
        """
        Broadcast a JSON payload to all connections (or all in a room).

        Args:
            data: JSON-serialisable payload.
            room: If given, only connections in that room receive the message.

        Returns:
            Number of connections successfully reached.
        """
        if room is not None:
            targets = list(self._rooms.get(room, set()))
        else:
            targets = list(self._connections.keys())

        sent = 0
        for cid in targets:
            if await self.send_json(cid, data):
                sent += 1
        return sent

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def room_members(self, room: str) -> set[str]:
        return set(self._rooms.get(room, set()))

    # ------------------------------------------------------------------
    # Redis pub/sub bridge (placeholder — implement in Phase 1)
    # ------------------------------------------------------------------

    async def publish_to_redis(self, channel: str, data: Any) -> None:
        """
        Publish an event to a Redis channel.

        TODO (Phase 1): Inject Redis client, serialise *data*, and call
        ``redis.publish(channel, json.dumps(data))``.
        """
        logger.debug(
            "Redis publish placeholder",
            channel=channel,
            data=data,
        )

    async def subscribe_to_redis(self, channel: str) -> None:
        """
        Subscribe to a Redis channel and forward messages to local connections.

        TODO (Phase 1): Create a background task that reads from a Redis
        pub/sub subscription and calls ``broadcast_json`` for each message.
        """
        logger.debug("Redis subscribe placeholder", channel=channel)


# Module-level singleton
ws_manager = ConnectionManager()
