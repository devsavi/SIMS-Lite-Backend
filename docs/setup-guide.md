# SIMS Lite Backend — Setup Guide

## Implemented Phases

| Phase | Module | Status |
|---|---|---|
| Phase 1 | Authentication & User Management | ✅ Complete |
| Phase 2 | Master Data Management | ✅ Complete |
| Phase 3 | Procurement (PO, GRN, Inventory) | ✅ Complete |

---

## Prerequisites

| Tool | Minimum Version |
|---|---|
| Python | 3.11+ |
| Docker | 24+ |
| Docker Compose | v2 (plugin) |
| Git | Any recent |

---

## 1. Clone and enter the project

```bash
git clone <repo-url> sims-lite-backend
cd sims-lite-backend
```

---

## 2. Create a virtual environment

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

---

## 3. Install dependencies

```bash
pip install -r requirements-dev.txt
```

---

## 4. Configure environment

```bash
cp .env.example .env
# Edit .env if you need to change any defaults
```

Default values in `.env` match the Docker Compose service configuration,
so no changes are needed for local development.

---

## 5. Start infrastructure services

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 16** on port `5432`
- **Redis 7** on port `6379`
- **MinIO** on port `9000` (API) and `9001` (web console)

Verify all services are healthy:

```bash
docker compose ps
```

---

## 6. Run database migrations

```bash
alembic upgrade head
```

---

## 7. Start the application

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or use the convenience script:

```bash
bash scripts/start.sh
```

---

## 8. Verify

| URL | Description |
|---|---|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/api/v1/health | Liveness probe |
| http://localhost:8000/api/v1/system/health | Deep readiness probe |
| http://localhost:9011 | MinIO web console (minioadmin / minioadmin) |

---

## Running tests

```bash
# All tests (182 tests across Phase 1 + Phase 2 + Phase 3)
pytest

# Unit tests only (no external services needed)
pytest tests/unit/

# Phase 3 procurement tests
pytest tests/unit/test_procurement_service.py tests/api/test_procurement_endpoints.py -v

# Phase 2 master data tests only
pytest tests/unit/test_master_data_service.py tests/unit/test_master_data_barcode_report.py tests/api/test_master_data_endpoints.py -v

# With coverage
pytest --cov=app --cov-report=term-missing

# Single file
pytest tests/api/test_health.py -v
```

---

## Phase 3 — Procurement quick-start

After applying migrations (`alembic upgrade head`), the procurement workflow is available immediately.

**Default permissions by role:**

| Role | procurement:read | procurement:write | procurement:approve |
|------|:---:|:---:|:---:|
| ADMIN | ✅ | ✅ | ✅ |
| OFFICER | ✅ | ✅ | ❌ |
| STORE_KEEPER | ✅ | ❌ | ❌ |

**Typical workflow:**

```
POST   /api/v1/purchase-orders/          → create DRAFT PO
PATCH  /api/v1/purchase-orders/{id}/submit   → SUBMITTED
PATCH  /api/v1/purchase-orders/{id}/approve  → APPROVED (Admin)
POST   /api/v1/purchase-orders/{id}/email    → email to supplier
POST   /api/v1/grns/                     → create DRAFT GRN
PATCH  /api/v1/grns/{id}/submit          → SUBMITTED
PATCH  /api/v1/grns/{id}/approve         → APPROVED + inventory posted (Admin)
GET    /api/v1/inventory/{product_id}/stock  → current stock level
```

**Reports & Dashboard:**

```
GET /api/v1/procurement/dashboard
GET /api/v1/procurement/reports/purchase-orders
GET /api/v1/procurement/reports/grns
GET /api/v1/procurement/reports/supplier-purchases
```

---

## Stopping infrastructure

```bash
# Stop containers, keep data volumes
docker compose down

# Stop and delete all data
docker compose down -v
```
