"""
WebSocket connection manager — Phase 6A (enhanced).

Tracks all active WebSocket connections and provides:
  - Personal (user) channels
  - Role-based channels
  - Global broadcast channel
  - Redis Pub/Sub bridge for horizontal scaling

Architecture
------------
Connections are tracked by three indices:
  connection_id → WebSocket            (all connections)
  user_id       → set[connection_id]   (personal channels)
  role          → set[connection_id]   (role channels)
  room          → set[connection_id]   (generic rooms, legacy support)

Redis Pub/Sub channels:
  notifications:user:<user_id>    — personal
  notifications:role:<role_name>  — role-based
  notifications:broadcast         — everyone
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.core.logging import get_logger

logger = get_logger(__name__)

# Redis channel names
_CHANNEL_BROADCAST = "notifications:broadcast"

# A per-process ID used to skip re-delivery of messages published by this worker
_WORKER_ID = str(uuid.uuid4())


def _user_channel(user_id: str) -> str:
    return f"notifications:user:{user_id}"


def _role_channel(role: str) -> str:
    return f"notifications:role:{role}"


class ConnectionManager:
    """
    In-process WebSocket connection registry with Redis Pub/Sub bridge.

    Thread-safety note: asyncio is single-threaded per event loop so
    the plain dict/set operations here are safe without locks.  If you
    run multiple workers you **must** use the Redis pub/sub bridge.
    """

    def __init__(self) -> None:
        # connection_id → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # room_name → set of connection_ids  (generic rooms)
        self._rooms: dict[str, set[str]] = defaultdict(set)
        # user_id (str) → set of connection_ids
        self._user_connections: dict[str, set[str]] = defaultdict(set)
        # role_name → set of connection_ids
        self._role_connections: dict[str, set[str]] = defaultdict(set)
        # Redis subscriber task handle
        self._redis_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        websocket: WebSocket,
        *,
        room: str | None = None,
        user_id: str | None = None,
        role: str | None = None,
    ) -> str:
        """
        Accept the WebSocket upgrade and register the connection.

        Args:
            websocket: The incoming WebSocket connection.
            room:      Optional generic room / channel name.
            user_id:   Authenticated user ID string (enables personal channel).
            role:      User's primary role name (enables role channel).

        Returns:
            A unique connection ID for this socket.
        """
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        self._connections[connection_id] = websocket

        if room:
            self._rooms[room].add(connection_id)
        if user_id:
            self._user_connections[user_id].add(connection_id)
        if role:
            self._role_connections[role].add(connection_id)

        logger.info(
            "WebSocket connected",
            connection_id=connection_id,
            user_id=user_id,
            role=role,
            room=room,
            total=len(self._connections),
        )
        return connection_id

    def disconnect(
        self,
        connection_id: str,
        *,
        user_id: str | None = None,
        role: str | None = None,
    ) -> None:
        """Deregister a connection (does not close the socket)."""
        self._connections.pop(connection_id, None)

        # Remove from all rooms
        for members in self._rooms.values():
            members.discard(connection_id)

        # Remove from user channels
        if user_id:
            self._user_connections[user_id].discard(connection_id)
        else:
            for members in self._user_connections.values():
                members.discard(connection_id)

        # Remove from role channels
        if role:
            self._role_connections[role].discard(connection_id)
        else:
            for members in self._role_connections.values():
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

    async def send_to_user(self, user_id: str, data: Any) -> int:
        """
        Send a message to all active connections for a specific user.

        Returns:
            Number of connections successfully reached.
        """
        targets = list(self._user_connections.get(user_id, set()))
        sent = 0
        for cid in targets:
            if await self.send_json(cid, data):
                sent += 1
        logger.debug(
            "Sent to user",
            user_id=user_id,
            connections=len(targets),
            sent=sent,
        )
        return sent

    async def send_to_role(self, role: str, data: Any) -> int:
        """
        Send a message to all connections belonging to a role.

        Returns:
            Number of connections successfully reached.
        """
        targets = list(self._role_connections.get(role, set()))
        sent = 0
        for cid in targets:
            if await self.send_json(cid, data):
                sent += 1
        logger.debug(
            "Sent to role",
            role=role,
            connections=len(targets),
            sent=sent,
        )
        return sent

    async def broadcast_to_all(self, data: Any) -> int:
        """
        Send a message to every connected client.

        Returns:
            Number of connections successfully reached.
        """
        targets = list(self._connections.keys())
        sent = 0
        for cid in targets:
            if await self.send_json(cid, data):
                sent += 1
        logger.debug("Broadcast to all", connections=len(targets), sent=sent)
        return sent

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def room_members(self, room: str) -> set[str]:
        return set(self._rooms.get(room, set()))

    def user_connections(self, user_id: str) -> set[str]:
        return set(self._user_connections.get(user_id, set()))

    def role_connections(self, role: str) -> set[str]:
        return set(self._role_connections.get(role, set()))

    # ------------------------------------------------------------------
    # Redis Pub/Sub bridge
    # ------------------------------------------------------------------

    async def publish_to_redis(self, channel: str, data: Any) -> None:
        """Publish an event to a Redis channel (tagged with this worker's ID)."""
        try:
            from app.core.redis import get_redis_client

            redis = get_redis_client()
            envelope = {"_worker": _WORKER_ID, "data": data}
            payload = json.dumps(envelope, default=str)
            await redis.publish(channel, payload)
            logger.debug("Redis published", channel=channel)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis publish failed", channel=channel, error=str(exc))

    async def publish_user_notification(self, user_id: str, data: Any) -> None:
        """Publish a personal notification to Redis + deliver locally."""
        # Deliver to locally connected clients immediately
        await self.send_to_user(user_id, data)
        # Also publish to Redis for other worker instances
        await self.publish_to_redis(_user_channel(user_id), data)

    async def publish_role_notification(self, role: str, data: Any) -> None:
        """Publish a role notification to Redis + deliver locally."""
        await self.send_to_role(role, data)
        await self.publish_to_redis(_role_channel(role), data)

    async def publish_broadcast(self, data: Any) -> None:
        """Publish a broadcast notification to Redis + deliver locally."""
        await self.broadcast_to_all(data)
        await self.publish_to_redis(_CHANNEL_BROADCAST, data)

    async def start_redis_subscriber(self) -> None:
        """
        Start a background task that subscribes to Redis Pub/Sub channels
        and forwards messages to local WebSocket connections.

        Called once at application startup.
        """
        if self._redis_task and not self._redis_task.done():
            return  # already running

        self._redis_task = asyncio.create_task(
            self._redis_subscriber_loop(),
            name="ws-redis-subscriber",
        )
        logger.info("Redis WebSocket subscriber started")

    async def stop_redis_subscriber(self) -> None:
        """Cancel the Redis subscriber background task."""
        if self._redis_task and not self._redis_task.done():
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass
        self._redis_task = None
        logger.info("Redis WebSocket subscriber stopped")

    async def _redis_subscriber_loop(self) -> None:
        """
        Background loop: subscribe to all notification channels via Redis
        Pub/Sub and forward messages to local WebSocket clients.
        """
        try:
            from app.core.redis import get_redis_client

            redis = get_redis_client()
            # Use a dedicated pub/sub connection
            pubsub = redis.pubsub()
            await pubsub.psubscribe("notifications:*")

            logger.info("Redis Pub/Sub subscriber active on notifications:*")

            async for raw_message in pubsub.listen():
                if raw_message["type"] not in ("message", "pmessage"):
                    continue

                channel: str = raw_message.get("channel", "") or ""
                raw_data = raw_message.get("data", "{}")

                try:
                    envelope = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    continue

                # Skip messages published by this worker (already delivered locally)
                if isinstance(envelope, dict) and envelope.get("_worker") == _WORKER_ID:
                    continue

                # Unwrap the data payload
                data = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope

                # Route based on channel pattern
                if channel == _CHANNEL_BROADCAST:
                    # Messages on the broadcast channel came from another worker.
                    # Deliver to all local connections.
                    await self.broadcast_to_all(data)
                elif channel.startswith("notifications:user:"):
                    uid = channel[len("notifications:user:"):]
                    # Deliver to locally connected clients of this user.
                    await self.send_to_user(uid, data)
                elif channel.startswith("notifications:role:"):
                    role = channel[len("notifications:role:"):]
                    # Deliver to locally connected clients of this role.
                    await self.send_to_role(role, data)

        except asyncio.CancelledError:
            logger.info("Redis subscriber cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Redis subscriber crashed", error=str(exc))


# Module-level singleton
ws_manager = ConnectionManager()
