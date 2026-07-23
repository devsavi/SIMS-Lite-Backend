# SIMS Lite Backend — Architecture

## Overview

SIMS Lite Backend is a modular, async-first FastAPI application designed for
school information and procurement management.

| Phase | Module | Status |
|---|---|---|
| Phase 1 | Authentication & User Management | ✅ Complete |
| Phase 2 | Master Data Management | ✅ Complete |

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
│   ├── security.py         # JWT + password helpers
│   ├── deps.py             # FastAPI dependency functions (auth, RBAC)
│   ├── seeder.py           # Idempotent DB seeder (roles, perms, superuser)
│   └── redis.py            # Redis client lifecycle
├── api/
│   └── v1/
│       ├── router.py       # Assembles all v1 endpoint routers
│       └── endpoints/
│           ├── health.py        # GET /api/v1/health
│           ├── system.py        # GET /api/v1/system/health
│           ├── websocket.py
│           ├── auth.py          # Phase 1: JWT auth flows
│           ├── users.py         # Phase 1: user management
│           ├── roles.py         # Phase 1: role management
│           ├── permissions.py   # Phase 1: permission management
│           ├── profile.py       # Phase 1: self-service profile
│           ├── categories.py    # Phase 2: category management
│           ├── brands.py        # Phase 2: brand management
│           ├── uoms.py          # Phase 2: unit of measure management
│           ├── suppliers.py     # Phase 2: supplier management
│           ├── products.py      # Phase 2: product catalogue + images + barcode
│           └── reports.py       # Phase 2: Excel report export
├── database/
│   ├── base.py             # DeclarativeBase + TimestampMixin + UUIDMixin
│   ├── engine.py           # Async engine, session factory, get_db dep
│   └── health.py           # DB ping utility
├── models/
│   ├── user.py             # Phase 1: User, Role, Permission, RefreshToken
│   ├── audit_log.py        # Phase 1: AuditLog
│   └── master_data.py      # Phase 2: Category, Brand, UoM, Supplier, Product
├── schemas/
│   ├── base.py             # SuccessResponse, PaginatedResponse, ErrorResponse
│   ├── auth.py             # Phase 1: auth request/response schemas
│   ├── user.py             # Phase 1: user schemas
│   └── master_data.py      # Phase 2: master data schemas
├── services/
│   ├── auth.py             # Phase 1: authentication business logic
│   ├── user.py             # Phase 1: user management business logic
│   ├── email.py            # Phase 1: email dispatch
│   ├── role.py             # Phase 1: role/permission management
│   ├── master_data.py      # Phase 2: category/brand/uom/supplier/product logic
│   └── report.py           # Phase 2: Excel report generation
├── repositories/
│   ├── base.py             # Generic async CRUD repository
│   ├── user.py             # Phase 1: user/role/permission repositories
│   ├── audit_log.py        # Phase 1: append-only audit log repository
│   └── master_data.py      # Phase 2: master data repositories
├── websockets/
│   ├── manager.py          # ConnectionManager singleton
│   └── events.py           # EventType enum + WebSocketEvent schema
├── storage/
│   └── minio_client.py     # StorageService (upload/delete/presign)
├── middleware/
│   └── logging.py          # RequestLoggingMiddleware
└── tasks/                  # Background task scaffold (future phases)
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
| Barcode generation | python-barcode | 0.15.1 |
| Excel reports | openpyxl | 3.1.5 |
| Image processing | Pillow | 10.4.0 |
| Containerisation | Docker Compose | v3.9 |
| Testing | pytest + pytest-asyncio | 8.2 / 0.23 |
