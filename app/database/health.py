"""Database health-check utility."""

from sqlalchemy import text

from app.core.logging import get_logger
from app.database.engine import get_engine

logger = get_logger(__name__)


async def check_database() -> dict:
    """
    Ping the database and return a status dict.

    Returns:
        {"status": "ok", "latency_ms": float}  on success
        {"status": "error", "error": str}       on failure
    """
    import time

    engine = get_engine()
    start = time.monotonic()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = round((time.monotonic() - start) * 1000, 2)
        return {"status": "ok", "latency_ms": latency}
    except Exception as exc:  # noqa: BLE001
        logger.error("Database health check failed", error=str(exc))
        return {"status": "error", "error": str(exc)}
