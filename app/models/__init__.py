"""
ORM model registry.

Import all models here so Alembic can discover every table via
Base.metadata when ``import app.models`` is executed in env.py.
"""

from app.models import user  # noqa: F401
from app.models import audit_log  # noqa: F401
