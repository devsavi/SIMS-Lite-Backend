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

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

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
# FastAPI application
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def app_instance():
    """
    Create the FastAPI application without running the lifespan.

    For integration tests that need real services, use the ``live_app``
    fixture instead (defined in tests/integration/conftest.py).
    """
    from app.main import create_app

    return create_app()


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
