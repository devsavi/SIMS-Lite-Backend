"""
Async SQLAlchemy engine and session factory.

The engine is created once at application startup via the lifespan handler
and torn down at shutdown.  All database access goes through AsyncSession
objects yielded by the `get_db` dependency.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singletons — set during lifespan startup
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine() -> AsyncEngine:
    """
    Create and return the async SQLAlchemy engine.

    Connection pool is tuned from application settings.
    """
    return create_async_engine(
        settings.db.url,
        echo=settings.db.echo,
        pool_size=settings.db.pool_size,
        max_overflow=settings.db.max_overflow,
        pool_timeout=settings.db.pool_timeout,
        pool_recycle=settings.db.pool_recycle,
        pool_pre_ping=True,  # detect stale connections
    )


def get_engine() -> AsyncEngine:
    """Return the active engine, raising if not yet initialised."""
    if _engine is None:
        raise RuntimeError("Database engine not initialised. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the active session factory, raising if not yet initialised."""
    if _session_factory is None:
        raise RuntimeError("Session factory not initialised. Call init_db() first.")
    return _session_factory


async def init_db() -> None:
    """Initialise the engine and session factory. Called once at startup."""
    global _engine, _session_factory  # noqa: PLW0603

    logger.info("Initialising database connection pool", url=settings.db.url.split("@")[-1])

    _engine = create_engine()
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    logger.info("Database connection pool ready")


async def close_db() -> None:
    """Dispose the engine and release all pooled connections."""
    global _engine, _session_factory  # noqa: PLW0603

    if _engine is not None:
        logger.info("Closing database connection pool")
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session.

    Commits on clean exit, rolls back on any exception, and always
    closes the session so connections are returned to the pool.

    Usage::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
