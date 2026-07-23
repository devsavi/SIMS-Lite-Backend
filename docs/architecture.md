# SIMS Lite Backend — Architecture

## Overview

SIMS Lite Backend is a modular, async-first FastAPI application designed for
school information management. Phase 0 establishes the infrastructure foundation;
business modules are added in subsequent phases.

---

## High-Level Architecture

```mermaid
graph TB
    subgraph Client Layer
        WEB[Web Browser]
        MOB[Mobile App]
        WS_CLIENT[WebSocket Client]
    end

    subgraph API Gateway / Load Balancer
        LB[Nginx / AWS ALB]
    end

    subgraph Application Layer
        API[FastAPI App<br/>:8000]
    end

    subgraph Middleware Stack
        CORS[CORS Middleware]
        LOG[Request Logging Middleware]
    end

    subgraph Infrastructure Services
        PG[(PostgreSQL 16<br/>:5432)]
        REDIS[(Redis 7<br/>:6379)]
        MINIO[MinIO<br/>:9000]
    end

    WEB --> LB
    MOB --> LB
    WS_CLIENT --> LB
    LB --> API
    API --> CORS --> LOG
    API --> PG
    API --> REDIS
    API --> MINIO
```

---

## Request Lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as Middleware Stack
    participant R as Router
    participant S as Service
    participant Repo as Repository
    participant DB as PostgreSQL

    C->>MW: HTTP Request
    MW->>MW: Assign Request ID
    MW->>MW: Log Request
    MW->>R: Route to handler
    R->>S: Call service method
    S->>Repo: Query / mutate data
    Repo->>DB: SQL (async)
    DB-->>Repo: Result
    Repo-->>S: Domain object
    S-->>R: Response data
    R-->>MW: HTTP Response
    MW->>MW: Log duration + status
    MW-->>C: Response + X-Request-ID header
```

---

## Package Structure

```
app/
├── main.py                 # Application factory + lifespan
├── core/
│   ├── config.py           # Pydantic Settings (all env vars)
│   ├── logging.py          # Structured logging (structlog)
│   ├── exceptions.py       # Exception hierarchy + global handlers
│   ├── security.py         # JWT + password helpers (Phase 1 scaffold)
│   └── redis.py            # Redis client lifecycle
├── api/
│   └── v1/
│       ├── router.py       # Assembles all v1 endpoint routers
│       └── endpoints/
│           ├── health.py   # GET /api/v1/health
│           ├── system.py   # GET /api/v1/system/health
│           └── websocket.py
├── database/
│   ├── base.py             # DeclarativeBase + TimestampMixin + UUIDMixin
│   ├── engine.py           # Async engine, session factory, get_db dep
│   └── health.py           # DB ping utility
├── models/                 # SQLAlchemy ORM models (Phase 1+)
├── schemas/
│   └── base.py             # SuccessResponse, PaginatedResponse, ErrorResponse
├── services/               # Business logic layer (Phase 1+)
├── repositories/
│   └── base.py             # Generic async CRUD repository
├── websockets/
│   ├── manager.py          # ConnectionManager singleton
│   └── events.py           # EventType enum + WebSocketEvent schema
├── storage/
│   └── minio_client.py     # StorageService (upload/delete/presign)
├── middleware/
│   └── logging.py          # RequestLoggingMiddleware
└── tasks/                  # Background task scaffold (Phase 1+)
```

---

## Data Flow — Object Storage

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant SS as StorageService
    participant MIO as MinIO

    C->>API: POST /api/v1/files/upload
    API->>SS: storage.upload(name, data)
    SS->>MIO: put_object (thread pool)
    MIO-->>SS: ETag / version
    SS-->>API: object_name
    API-->>C: 201 { url: presigned_url }

    note over C,MIO: Download via pre-signed URL
    C->>SS: storage.get_presigned_url(name)
    SS->>MIO: presigned_get_object
    MIO-->>SS: signed URL (1h TTL)
    SS-->>C: URL
    C->>MIO: GET signed URL (direct)
```

---

## WebSocket Event Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant WS as WebSocket Endpoint
    participant MGR as ConnectionManager
    participant REDIS as Redis PubSub (Phase 1)

    C->>WS: WS Upgrade /api/v1/ws/connect
    WS->>MGR: connect(websocket, room)
    MGR-->>WS: connection_id
    WS-->>C: {"event": "system.connected", "payload": {"connection_id": "..."}}

    loop Message Loop
        C->>WS: {"event": "system.ping"}
        WS->>MGR: send_json(id, pong)
        MGR-->>C: {"event": "system.pong"}
    end

    note over MGR,REDIS: Phase 1 — Redis pub/sub bridge
    note over MGR,REDIS: publish_to_redis / subscribe_to_redis
```

---

## Layers and Responsibilities

| Layer | Location | Responsibility |
|---|---|---|
| API | `app/api/` | HTTP routing, request parsing, response serialisation |
| Service | `app/services/` | Business logic, orchestration, validation |
| Repository | `app/repositories/` | All database queries |
| Model | `app/models/` | SQLAlchemy ORM table definitions |
| Schema | `app/schemas/` | Pydantic I/O contracts |
| Core | `app/core/` | Config, logging, exceptions, security, Redis |
| Storage | `app/storage/` | MinIO operations |
| WebSocket | `app/websockets/` | Real-time connection management |
| Middleware | `app/middleware/` | Cross-cutting concerns |
| Tasks | `app/tasks/` | Background / async jobs |

---

## Technology Stack

| Component | Technology | Version |
|---|---|---|
| Web framework | FastAPI | 0.111 |
| ASGI server | Uvicorn | 0.29 |
| ORM | SQLAlchemy | 2.0 (async) |
| DB driver | asyncpg | 0.29 |
| Migrations | Alembic | 1.13 |
| Database | PostgreSQL | 16 |
| Cache / Pub-Sub | Redis | 7 |
| Object storage | MinIO | latest |
| Validation | Pydantic | v2 |
| Logging | structlog | 24.2 |
| Containerisation | Docker Compose | v3.9 |
| Testing | pytest + pytest-asyncio | 8.2 / 0.23 |
