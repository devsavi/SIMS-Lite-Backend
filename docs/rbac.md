# RBAC — Role-Based Access Control

## Overview

SIMS Lite implements Role-Based Access Control (RBAC) using a **roles → permissions** model. Users have one or more roles; roles grant a set of permissions; permissions define what actions are allowed on which resources.

---

## Data Model

```mermaid
erDiagram
    USERS {
        uuid id PK
        string email
        bool is_superuser
    }
    ROLES {
        uuid id PK
        string name
        bool is_system
    }
    PERMISSIONS {
        uuid id PK
        string name
        string resource
        string action
    }
    USER_ROLES {
        uuid user_id FK
        uuid role_id FK
    }
    ROLE_PERMISSIONS {
        uuid role_id FK
        uuid permission_id FK
    }

    USERS ||--o{ USER_ROLES : "has"
    USER_ROLES }o--|| ROLES : "maps to"
    ROLES ||--o{ ROLE_PERMISSIONS : "grants"
    ROLE_PERMISSIONS }o--|| PERMISSIONS : "maps to"
```

---

## Built-In System Roles

| Role | Description |
|------|-------------|
| `ADMIN` | Full system access — manages users, roles, and all data |
| `OFFICER` | Academic officer — read/write access to academic records and reports |
| `STORE_KEEPER` | Manages inventory and procurement orders |

System roles (`is_system=True`) cannot be deleted via the API.

---

## Permission Naming Convention

Permissions follow the `resource:action` format:

| Permission | Description |
|-----------|-------------|
| `users:read` | View user accounts |
| `users:write` | Create and update users |
| `users:delete` | Delete users |
| `roles:read` | View roles |
| `roles:write` | Create and update roles |
| `roles:delete` | Delete roles |
| `permissions:read` | View permissions |
| `permissions:write` | Create permissions |
| `audit_logs:read` | View audit logs |
| `reports:read` | View reports |
| `reports:export` | Export reports |
| `inventory:read` | View inventory |
| `inventory:write` | Manage inventory |
| `procurement:read` | View procurement orders |
| `procurement:write` | Create procurement orders |

---

## Role-Permission Mapping (Default)

| Permission | ADMIN | OFFICER | STORE_KEEPER |
|-----------|:-----:|:-------:|:------------:|
| `users:read` | ✅ | ✅ | |
| `users:write` | ✅ | | |
| `users:delete` | ✅ | | |
| `roles:read` | ✅ | | |
| `roles:write` | ✅ | | |
| `roles:delete` | ✅ | | |
| `permissions:read` | ✅ | | |
| `permissions:write` | ✅ | | |
| `audit_logs:read` | ✅ | | |
| `reports:read` | ✅ | ✅ | |
| `reports:export` | ✅ | ✅ | |
| `inventory:read` | ✅ | ✅ | ✅ |
| `inventory:write` | ✅ | | ✅ |
| `procurement:read` | ✅ | ✅ | ✅ |
| `procurement:write` | ✅ | ✅ | |

---

## Authorization Request Flow

```mermaid
flowchart TD
    A[Incoming Request] --> B{Has Bearer token?}
    B -- No --> C[401 Unauthorized]
    B -- Yes --> D{Valid JWT?}
    D -- No --> C
    D -- Yes --> E{User active?}
    E -- No --> F[403 Forbidden]
    E -- Yes --> G{Is superuser?}
    G -- Yes --> H[Allow]
    G -- No --> I{Has required role?}
    I -- Yes --> J{Has required permission?}
    I -- No --> F
    J -- Yes --> H
    J -- No --> F
    H --> K[Execute handler]
```

---

## Using RBAC in Code

### Require Authentication (any active user)

```python
from app.core.deps import get_current_user

@router.get("/data")
async def get_data(user: User = Depends(get_current_user)):
    ...
```

### Require a Role

```python
from app.core.deps import require_roles

@router.get("/admin-only")
async def admin(user: User = Depends(require_roles("ADMIN"))):
    ...

# Multiple allowed roles (OR logic)
@router.get("/reports")
async def reports(user: User = Depends(require_roles("ADMIN", "OFFICER"))):
    ...
```

### Require a Permission

```python
from app.core.deps import require_permission

@router.post("/inventory")
async def update_inventory(user: User = Depends(require_permission("inventory:write"))):
    ...
```

### Superuser Override

Superusers bypass all role and permission checks automatically.

---

## Managing Roles via API

All role management endpoints require the `ADMIN` role.

```bash
# List roles
GET /api/v1/roles/

# Create a role
POST /api/v1/roles/
{ "name": "AUDITOR", "description": "Read-only auditor", "permission_ids": [...] }

# Update a role's permissions
PUT /api/v1/roles/{role_id}
{ "permission_ids": [...] }

# Assign roles to a user
PUT /api/v1/users/{user_id}/roles
{ "role_ids": [...] }
```

---

## Superuser Account

On first startup, a default superuser is created:

| Field | Value |
|-------|-------|
| Email | `admin@sims.local` |
| Password | `Admin@1234!` |

**Change the password immediately after first login in any non-development environment.**
