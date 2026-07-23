"""
Audit log ORM model.

Every sensitive action (login, logout, create user, change password, etc.)
is recorded here for compliance and forensics.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDMixin


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """
    Immutable record of a user action or system event.

    Fields
    ------
    actor_id : UUID | None
        The user who performed the action. Null for anonymous/system events.
    action : str
        Short action code, e.g. ``auth.login``, ``user.create``,
        ``user.password_change``.
    resource_type : str | None
        Entity type affected, e.g. ``User``, ``Role``.
    resource_id : str | None
        Primary key of the affected entity (stored as string for flexibility).
    ip_address : str | None
        Client IP address at the time of the event.
    user_agent : str | None
        Client user-agent string.
    status : str
        Outcome: ``success`` or ``failure``.
    detail : dict | None
        Arbitrary structured context stored as JSONB.
    """

    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success", index=True
    )
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    actor: Mapped[Any] = relationship(
        "User",
        foreign_keys=[actor_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action} actor={self.actor_id} status={self.status}>"
