"""
Database seeder — Phase 1.

Seeds the initial system roles, permissions, and a superuser admin account.
Run at startup only if the data doesn't already exist (idempotent).

Call `seed_initial_data(session)` from the lifespan startup handler.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.user import Permission, Role, User

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# System roles
# ---------------------------------------------------------------------------

SYSTEM_ROLES: list[dict] = [
    {
        "name": "ADMIN",
        "description": "Full system access. Can manage users, roles, and all data.",
        "is_system": True,
    },
    {
        "name": "OFFICER",
        "description": "Academic officer with read/write access to records.",
        "is_system": True,
    },
    {
        "name": "STORE_KEEPER",
        "description": "Inventory and store management access.",
        "is_system": True,
    },
]

# ---------------------------------------------------------------------------
# Default permissions: resource:action pairs
# ---------------------------------------------------------------------------

SYSTEM_PERMISSIONS: list[dict] = [
    # User management
    {"resource": "users", "action": "read", "description": "View user accounts"},
    {"resource": "users", "action": "write", "description": "Create and update user accounts"},
    {"resource": "users", "action": "delete", "description": "Delete user accounts"},
    # Role management
    {"resource": "roles", "action": "read", "description": "View roles"},
    {"resource": "roles", "action": "write", "description": "Create and update roles"},
    {"resource": "roles", "action": "delete", "description": "Delete roles"},
    # Permission management
    {"resource": "permissions", "action": "read", "description": "View permissions"},
    {"resource": "permissions", "action": "write", "description": "Create permissions"},
    # Audit log
    {"resource": "audit_logs", "action": "read", "description": "View audit logs"},
    # Reports (placeholder for later phases)
    {"resource": "reports", "action": "read", "description": "View reports"},
    {"resource": "reports", "action": "export", "description": "Export reports"},
    # Inventory (placeholder for later phases)
    {"resource": "inventory", "action": "read", "description": "View inventory"},
    {"resource": "inventory", "action": "write", "description": "Manage inventory"},
    # Procurement — Phase 3
    {"resource": "procurement", "action": "read", "description": "View procurement orders"},
    {"resource": "procurement", "action": "write", "description": "Create and update procurement orders"},
    {"resource": "procurement", "action": "approve", "description": "Approve purchase orders and GRNs"},
    # Master data — Phase 2
    {"resource": "master_data", "action": "read", "description": "View master data"},
    {"resource": "master_data", "action": "write", "description": "Create and update master data"},
    {"resource": "master_data", "action": "delete", "description": "Delete master data"},
]

# Map role name → list of (resource, action) tuples it receives
ROLE_PERMISSION_MAP: dict[str, list[tuple[str, str]]] = {
    "ADMIN": [
        # Admins get everything
        ("users", "read"), ("users", "write"), ("users", "delete"),
        ("roles", "read"), ("roles", "write"), ("roles", "delete"),
        ("permissions", "read"), ("permissions", "write"),
        ("audit_logs", "read"),
        ("reports", "read"), ("reports", "export"),
        ("inventory", "read"), ("inventory", "write"),
        ("procurement", "read"), ("procurement", "write"), ("procurement", "approve"),
        # Phase 2 master data
        ("master_data", "read"), ("master_data", "write"), ("master_data", "delete"),
    ],
    "OFFICER": [
        ("users", "read"),
        ("reports", "read"), ("reports", "export"),
        ("inventory", "read"),
        ("procurement", "read"), ("procurement", "write"),
        # Phase 2 — read + write master data
        ("master_data", "read"), ("master_data", "write"),
    ],
    "STORE_KEEPER": [
        ("inventory", "read"), ("inventory", "write"),
        ("procurement", "read"),
        # Phase 2 — read-only master data
        ("master_data", "read"),
    ],
}


async def seed_initial_data(session: AsyncSession) -> None:
    """
    Idempotently seed roles, permissions, and the default superuser.

    Safe to call on every startup.
    """
    logger.info("Running database seeder…")

    # --- Permissions ---
    perm_map: dict[tuple[str, str], Permission] = {}
    for pdef in SYSTEM_PERMISSIONS:
        resource = pdef["resource"]
        action = pdef["action"]
        name = f"{resource}:{action}"

        result = await session.execute(
            select(Permission).where(Permission.name == name)
        )
        perm = result.scalar_one_or_none()
        if perm is None:
            perm = Permission(
                name=name,
                description=pdef.get("description"),
                resource=resource,
                action=action,
            )
            session.add(perm)
            await session.flush()
            logger.debug("Created permission", name=name)
        perm_map[(resource, action)] = perm

    # --- Roles ---
    role_map: dict[str, Role] = {}
    for rdef in SYSTEM_ROLES:
        result = await session.execute(
            select(Role)
            .where(Role.name == rdef["name"])
            .options(selectinload(Role.permissions))
        )
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(
                name=rdef["name"],
                description=rdef["description"],
                is_system=rdef["is_system"],
            )
            session.add(role)
            await session.flush()
            logger.debug("Created role", name=rdef["name"])
        role_map[rdef["name"]] = role

    await session.flush()

    # --- Assign permissions to roles ---
    for role_name, perm_pairs in ROLE_PERMISSION_MAP.items():
        role = role_map[role_name]
        # Reload with permissions eagerly
        result = await session.execute(
            select(Role)
            .where(Role.id == role.id)
            .options(selectinload(Role.permissions))
        )
        role = result.scalar_one()
        existing_perm_ids = {p.id for p in role.permissions}

        for resource, action in perm_pairs:
            perm = perm_map.get((resource, action))
            if perm and perm.id not in existing_perm_ids:
                role.permissions.append(perm)

        session.add(role)

    await session.flush()

    # --- Default superuser ---
    await _seed_superuser(session, role_map.get("ADMIN"))

    await session.commit()
    logger.info("Database seeder complete")


async def _seed_superuser(session: AsyncSession, admin_role: Role | None) -> None:
    """Create the default superuser if none exists."""
    result = await session.execute(
        select(User).where(User.is_superuser.is_(True))
    )
    existing = result.scalar_one_or_none()
    if existing:
        return  # already seeded

    # Use settings or fall back to safe defaults
    default_email = "admin@sims.local"
    default_password = "Admin@1234!"  # must be changed in production

    superuser = User(
        email=default_email,
        password_hash=hash_password(default_password),
        first_name="System",
        last_name="Administrator",
        is_active=True,
        is_verified=True,
        is_superuser=True,
    )
    session.add(superuser)
    await session.flush()

    if admin_role:
        result = await session.execute(
            select(User)
            .where(User.id == superuser.id)
            .options(selectinload(User.roles))
        )
        superuser = result.scalar_one()
        superuser.roles.append(admin_role)
        session.add(superuser)
        await session.flush()

    logger.info(
        "Default superuser created",
        email=default_email,
        note="CHANGE PASSWORD BEFORE GOING TO PRODUCTION",
    )
