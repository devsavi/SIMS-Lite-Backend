"""
Pytest configuration and shared fixtures.

Fixtures provided:
- ``settings``          — application settings (real, from .env.test or .env)
- ``app``               — FastAPI test application instance
- ``client``            — async HTTPX test client (no real DB/Redis/MinIO)
- ``db_session``        — async SQLAlchemy session backed by an in-memory SQLite
                          NOTE: requires asyncpg-compatible dialect for full tests;
                          use ``@pytest.mark.integration`` for tests that need Postgres.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Return application settings (reads .env)."""
    from app.core.config import get_settings

    return get_settings()


# ---------------------------------------------------------------------------
# Mock DB session
# ---------------------------------------------------------------------------


def _make_mock_db() -> AsyncSession:
    """Return a mock async DB session for use in tests."""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


async def _mock_get_db() -> AsyncGenerator[AsyncSession, None]:
    yield _make_mock_db()


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def app_instance():
    """
    Create the FastAPI application without running the lifespan.

    For integration tests that need real services, use the ``live_app``
    fixture instead (defined in tests/integration/conftest.py).

    The get_db dependency is overridden with a mock so that API tests
    don't need a running database.
    """
    from app.main import create_app
    from app.database.engine import get_db

    app = create_app()
    # Override DB dependency globally so all tests start with a mock session
    app.dependency_overrides[get_db] = _mock_get_db
    return app


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(app_instance):
    """
    Async HTTPX client that talks directly to the ASGI app.

    Dependencies that hit the database or Redis are overridden in
    individual test modules via ``app.dependency_overrides``.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://testserver",
    ) as ac:
        yield ac
