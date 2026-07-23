# SIMS Lite Backend — Development Guide

## Project conventions

### Python style

- Formatter: **black** (`black .`)
- Linter: **ruff** (`ruff check . --fix`)
- Type checker: **mypy** (`mypy app/`)
- Target Python: **3.12+**
- Line length: **88** characters

Run all checks at once:

```bash
black . && ruff check . --fix && mypy app/
```

---

## Adding a new feature module (Phase 1+)

Follow this pattern for every domain module (e.g., `users`, `courses`):

### 1. ORM model — `app/models/<module>.py`

```python
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base, TimestampMixin, UUIDMixin

class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    ...
```

Register it in `app/models/__init__.py`:

```python
from app.models import user  # noqa: F401
```

### 2. Schemas — `app/schemas/<module>.py`

```python
from app.schemas.base import AppBaseModel

class UserCreate(AppBaseModel):
    email: str
    ...

class UserRead(AppBaseModel):
    id: uuid.UUID
    email: str
    ...
```

### 3. Repository — `app/repositories/<module>.py`

```python
from app.repositories.base import BaseRepository
from app.models.user import User

class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        ...
```

### 4. Service — `app/services/<module>.py`

```python
class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self.repo = repo

    async def create_user(self, data: UserCreate) -> UserRead:
        ...
```

### 5. Router — `app/api/v1/endpoints/<module>.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.engine import get_db

router = APIRouter()

@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    ...
```

Register in `app/api/v1/router.py`:

```python
from app.api.v1.endpoints import users
api_router.include_router(users.router, prefix="/users", tags=["Users"])
```

### 6. Migration

```bash
alembic revision --autogenerate -m "add users table"
alembic upgrade head
```

---

## Database session usage

Use the `get_db` dependency in route handlers:

```python
from app.database.engine import get_db
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/items")
async def list_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item))
    return result.scalars().all()
```

The session **auto-commits** on clean exit and **rolls back** on any exception.

---

## Redis usage

```python
from redis.asyncio import Redis
from app.core.redis import get_redis

@router.get("/cached")
async def cached_endpoint(redis: Redis = Depends(get_redis)):
    value = await redis.get("my-key")
    ...
```

---

## MinIO / file uploads

```python
from app.storage.minio_client import storage_service

object_name = await storage_service.upload(
    object_name="uploads/photo.jpg",
    data=file.file,
    content_type=file.content_type,
)
url = await storage_service.get_presigned_url(object_name)
```

---

## WebSocket events

Add new event types to `app/websockets/events.py`:

```python
class EventType(StrEnum):
    ...
    CHAT_MESSAGE = "chat.message"
```

Handle them in the WebSocket endpoint or in a dedicated event handler
registered on `ws_manager`.

---

## Error handling

Raise domain exceptions directly in services or route handlers:

```python
from app.core.exceptions import NotFoundError

async def get_user(user_id: uuid.UUID) -> User:
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    return user
```

The global exception handler converts these to structured JSON responses
automatically.

---

## Writing tests

### Unit test (no DB/Redis)

```python
# tests/unit/test_my_service.py
import pytest
from unittest.mock import AsyncMock

async def test_something():
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None
    service = MyService(mock_repo)
    with pytest.raises(NotFoundError):
        await service.get(some_id)
```

### API test (ASGI test client)

```python
# tests/api/test_my_endpoint.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_endpoint(client: AsyncClient):
    response = await client.get("/api/v1/my-endpoint")
    assert response.status_code == 200
```

Override dependencies for isolation:

```python
app_instance.dependency_overrides[get_db] = lambda: mock_session
```

---

## Environment variables reference

See `.env.example` for the full list with descriptions.

Key variables:

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | `development`, `staging`, `production` |
| `APP_DEBUG` | `true` | Enables debug mode |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_NAME` | `sims_lite` | Database name |
| `REDIS_HOST` | `localhost` | Redis host |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO endpoint |
| `LOG_FORMAT` | `json` | `json` or `console` |

---

## Useful commands

```bash
# Start infrastructure
docker compose up -d

# Apply migrations
alembic upgrade head

# Generate a new migration
alembic revision --autogenerate -m "description"

# Roll back one step
alembic downgrade -1

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Format + lint
black . && ruff check . --fix

# Type check
mypy app/

# Show Alembic history
alembic history --verbose
```
