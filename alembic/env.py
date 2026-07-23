"""
Alembic migration environment.

Reads the database URL from application settings so a single source of
truth is maintained.  Supports both:

- ``alembic upgrade head``  (online, async engine via asyncpg)
- ``alembic revision --autogenerate``  (offline, inspects metadata)
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Import Base so all model metadata is registered
from app.database.base import Base  # noqa: F401

# Import all model modules so Alembic can detect them
# Phase 1+: add model imports here, e.g.:
# from app.models import user  # noqa: F401
import app.models  # noqa: F401

from app.core.config import settings

# ---------------------------------------------------------------------------
# Alembic Config object (gives access to alembic.ini values)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate support
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode (no live DB connection; generates SQL script)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    context.configure(
        url=settings.db.sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode (connects to the database via asyncpg)
# ---------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine (asyncpg driver)."""
    engine = create_async_engine(
        settings.db.url,  # postgresql+asyncpg://...
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
