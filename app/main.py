"""
SIMS Lite Backend — FastAPI application factory.

Startup sequence
----------------
1. Configure structured logging
2. Register global exception handlers
3. Attach middleware (CORS → request logging)
4. Mount API v1 router at /api/v1
5. Expose lifespan to initialise / tear down DB, Redis, MinIO

Docs
----
Swagger UI : /docs
ReDoc      : /redoc
OpenAPI    : /openapi.json
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging

# Initialise logging before anything else
setup_logging(log_level=settings.log_level, log_format=settings.log_format)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Everything before the ``yield`` runs at startup;
    everything after runs at shutdown.
    """
    # --- Startup ---
    logger.info("Starting up SIMS Lite Backend", env=settings.app_env)

    from app.database.engine import init_db
    from app.core.redis import init_redis
    from app.storage.minio_client import init_minio

    await init_db()
    await init_redis()
    await init_minio()

    logger.info("All services initialised — application ready")

    yield  # Application is now serving requests

    # --- Shutdown ---
    logger.info("Shutting down SIMS Lite Backend")

    from app.database.engine import close_db
    from app.core.redis import close_redis
    from app.storage.minio_client import close_minio

    await close_db()
    await close_redis()
    await close_minio()

    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description=(
            "SIMS Lite — School Information Management System backend API.\n\n"
            "**Phase 0**: Infrastructure foundation only.\n"
            "Business modules are added in subsequent phases."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ #
    # Exception handlers (register before middleware)                      #
    # ------------------------------------------------------------------ #
    register_exception_handlers(app)

    # ------------------------------------------------------------------ #
    # Middleware  (applied in reverse order — last added = first executed) #
    # ------------------------------------------------------------------ #

    # 1. CORS (outermost so it runs before auth/logging)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    # 2. Request logging
    from app.middleware.logging import RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware)

    # ------------------------------------------------------------------ #
    # Routers                                                              #
    # ------------------------------------------------------------------ #
    from app.api.v1.router import api_router
    app.include_router(api_router, prefix="/api/v1")

    # ------------------------------------------------------------------ #
    # Root redirect                                                        #
    # ------------------------------------------------------------------ #
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    logger.info("Application created", docs="/docs", redoc="/redoc")
    return app


# Instantiate the application (picked up by uvicorn as ``app.main:app``)
app = create_app()
