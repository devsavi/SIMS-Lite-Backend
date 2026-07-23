"""
ORM model registry.

Import all models here so Alembic can discover every table via
Base.metadata when ``import app.models`` is executed in env.py.
"""

from app.models import user  # noqa: F401
from app.models import audit_log  # noqa: F401
from app.models import master_data  # noqa: F401  Phase 2
from app.models import procurement  # noqa: F401  Phase 3
from app.models import inventory  # noqa: F401  Phase 4
from app.models import stock_release  # noqa: F401  Phase 5
