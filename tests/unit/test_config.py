"""Unit tests for application configuration."""

import pytest

from app.core.config import Settings


def test_settings_loads():
    """Settings can be instantiated without errors."""
    s = Settings()
    assert s.app_name


def test_database_url_format():
    """Database URL uses asyncpg driver."""
    s = Settings()
    assert s.db.url.startswith("postgresql+asyncpg://")


def test_database_sync_url_format():
    """Sync DB URL uses psycopg2 (required by Alembic)."""
    s = Settings()
    assert s.db.sync_url.startswith("postgresql+psycopg2://")


def test_redis_url_no_password():
    """Redis URL with no password omits auth section."""
    s = Settings()
    if not s.redis.password:
        assert "@" not in s.redis.url


def test_is_development_flag():
    """Development environment flag is set correctly."""
    s = Settings()
    # In test runs the env defaults to development
    if s.app_env == "development":
        assert s.is_development is True
        assert s.is_production is False
