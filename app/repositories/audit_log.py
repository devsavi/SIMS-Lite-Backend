"""
Audit log repository.

Provides write-only (append) and read queries for the audit_logs table.
Audit logs are immutable — there is no update or delete operation here.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Append-only repository for audit log entries."""

    model = AuditLog

    async def log(
        self,
        *,
        action: str,
        status: str = "success",
        actor_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Append a new audit log entry."""
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            detail=detail,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def get_for_actor(
        self,
        actor_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AuditLog]:
        """Return paginated audit logs for a specific actor."""
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.actor_id == actor_id)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_paginated(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        action_filter: str | None = None,
    ) -> tuple[list[AuditLog], int]:
        """Return (logs, total) with optional action prefix filter."""
        from sqlalchemy import func

        query = select(AuditLog)
        if action_filter:
            query = query.where(AuditLog.action.startswith(action_filter))

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar_one()

        result = await self.session.execute(
            query.order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total
