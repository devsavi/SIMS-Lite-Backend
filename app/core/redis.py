"""
Redis client factory and lifecycle management.

The module maintains a single ``redis.asyncio.Redis`` instance that is
created at startup and closed at shutdown.  A ``get_redis`` dependency
exposes the client to route handlers.

The client is intentionally kept thin here.  Cache helpers, pub/sub
channels, and job-queue wrappers are built on top of this foundation
in their respective layers.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis_client: Redis | None = None


async def init_redis() -> None:
    """Create the Redis connection pool. Called once at application startup."""
    global _redis_client  # noqa: PLW0603

    logger.info(
        "Connecting to Redis",
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.db,
    )
    _redis_client = aioredis.from_url(
        settings.redis.url,
        max_connections=settings.redis.max_connections,
        decode_responses=True,
        encoding="utf-8",
    )
    # Verify the connection is live
    await _redis_client.ping()
    logger.info("Redis connection established")


async def close_redis() -> None:
    """Close the Redis connection pool. Called at application shutdown."""
    global _redis_client  # noqa: PLW0603

    if _redis_client is not None:
        logger.info("Closing Redis connection")
        await _redis_client.aclose()
        _redis_client = None


def get_redis_client() -> Redis:
    """Return the active Redis client, raising if not initialised."""
    if _redis_client is None:
        raise RuntimeError("Redis client not initialised. Call init_redis() first.")
    return _redis_client


async def get_redis() -> Redis:
    """
    FastAPI dependency that provides the Redis client.

    Usage::

        @router.get("/items")
        async def handler(redis: Redis = Depends(get_redis)):
            value = await redis.get("key")
    """
    return get_redis_client()


async def check_redis() -> dict:
    """
    Ping Redis and return a status dict.

    Returns:
        {"status": "ok", "latency_ms": float}  on success
        {"status": "error", "error": str}       on failure
    """
    import time

    client = get_redis_client()
    start = time.monotonic()
    try:
        await client.ping()
        latency = round((time.monotonic() - start) * 1000, 2)
        return {"status": "ok", "latency_ms": latency}
    except RedisError as exc:
        logger.error("Redis health check failed", error=str(exc))
        return {"status": "error", "error": str(exc)}
