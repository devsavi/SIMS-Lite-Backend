"""
Generic async repository base class.

Provides standard CRUD operations for any SQLAlchemy ORM model.
Feature repositories inherit from this and add domain-specific queries.

Usage::

    class UserRepository(BaseRepository[User]):
        model = User

    # In a service:
    repo = UserRepository(db_session)
    user = await repo.get_by_id(user_id)
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic CRUD repository for SQLAlchemy async sessions."""

    model: type[ModelT]  # subclasses must assign this

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, pk: uuid.UUID | int) -> ModelT | None:
        """Fetch a single record by primary key."""
        return await self.session.get(self.model, pk)

    async def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ModelT]:
        """Fetch a paginated list of all records."""
        result = await self.session.execute(
            select(self.model).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelT:
        """Create and persist a new record."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()  # populate DB-generated defaults
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelT, **kwargs: Any) -> ModelT:
        """Update fields on an existing record."""
        for key, value in kwargs.items():
            setattr(instance, key, value)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        """Hard-delete a record."""
        await self.session.delete(instance)
        await self.session.flush()

    async def count(self) -> int:
        """Return the total number of records."""
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar_one()
