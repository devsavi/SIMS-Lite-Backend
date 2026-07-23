"""
Declarative base and reusable mixin columns.

All ORM models should:
1. Inherit from ``Base``
2. Optionally mix in ``TimestampMixin`` for created_at / updated_at
3. Optionally mix in ``UUIDMixin`` for UUID primary keys

Import this module in every model file so Alembic can discover
all tables via ``Base.metadata``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy declarative base."""


class TimestampMixin:
    """
    Adds ``created_at`` and ``updated_at`` columns.

    Both columns use the database server clock so they are accurate
    regardless of application timezone settings.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    """
    Adds a UUID v4 primary key column named ``id``.

    Using UUIDs as primary keys makes it safe to generate IDs
    client-side and simplifies horizontal sharding.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
