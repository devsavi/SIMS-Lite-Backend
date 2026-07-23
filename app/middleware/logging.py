"""
Request logging middleware.

Logs every HTTP request with:
- request_id  (injected into async context for downstream use)
- method / path / status
- response duration in ms
- client IP

The request ID is taken from the incoming ``X-Request-ID`` header if
present, otherwise a UUID is generated.  It is echoed back in the
``X-Request-ID`` response header.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger, set_request_id

logger = get_logger(__name__)

# Paths that should not be logged (reduces noise in health-check polling)
_SKIP_PATHS: frozenset[str] = frozenset({"/api/v1/health", "/favicon.ico"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured request/response logging with request-ID propagation."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Resolve or generate request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(request_id)

        start = time.monotonic()
        status_code = 500  # default; overwritten on success

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            raise
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            path = request.url.path

            if path not in _SKIP_PATHS:
                logger.info(
                    "HTTP request",
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    client_host=request.client.host if request.client else None,
                    request_id=request_id,
                )

        response.headers["X-Request-ID"] = request_id
        return response
