"""
MinIO storage client and lifecycle management.

Wraps the official ``minio`` Python SDK in a thin async-compatible
façade.  Heavy I/O (upload, download) is offloaded to a thread pool
via ``asyncio.get_event_loop().run_in_executor`` so it does not block
the event loop.

Buckets:
    - ``sims-files``   — private uploads (served via pre-signed URLs)
    - ``sims-public``  — publicly readable assets
"""

from __future__ import annotations

import asyncio
import io
import time
from datetime import timedelta
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_minio_client: Minio | None = None


def _create_minio_client() -> Minio:
    return Minio(
        endpoint=settings.minio.endpoint,
        access_key=settings.minio.access_key,
        secret_key=settings.minio.secret_key,
        secure=settings.minio.use_ssl,
    )


async def init_minio() -> None:
    """
    Initialise the MinIO client and ensure required buckets exist.
    Called once at application startup.
    """
    global _minio_client  # noqa: PLW0603

    logger.info(
        "Connecting to MinIO",
        endpoint=settings.minio.endpoint,
        ssl=settings.minio.use_ssl,
    )
    _minio_client = _create_minio_client()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _ensure_buckets, _minio_client)
    logger.info("MinIO client ready")


def _ensure_buckets(client: Minio) -> None:
    """Create required buckets if they do not exist (sync, runs in executor)."""
    for bucket_name in (
        settings.minio.bucket_default,
        settings.minio.bucket_public,
    ):
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info("Created MinIO bucket", bucket=bucket_name)
        else:
            logger.debug("MinIO bucket already exists", bucket=bucket_name)


async def close_minio() -> None:
    """Release the MinIO client. Called at application shutdown."""
    global _minio_client  # noqa: PLW0603

    _minio_client = None
    logger.info("MinIO client closed")


def get_minio_client() -> Minio:
    """Return the active MinIO client, raising if not initialised."""
    if _minio_client is None:
        raise RuntimeError("MinIO client not initialised. Call init_minio() first.")
    return _minio_client


# ---------------------------------------------------------------------------
# Storage service helpers
# ---------------------------------------------------------------------------


class StorageService:
    """High-level async interface to MinIO object storage."""

    def __init__(self, bucket: str | None = None) -> None:
        self.bucket = bucket or settings.minio.bucket_default

    def _client(self) -> Minio:
        return get_minio_client()

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    async def upload(
        self,
        object_name: str,
        data: BinaryIO | bytes,
        content_type: str = "application/octet-stream",
        bucket: str | None = None,
    ) -> str:
        """
        Upload *data* to *object_name* and return the object name.

        Args:
            object_name: Target path inside the bucket (e.g. "uploads/photo.jpg").
            data:         File-like object or raw bytes.
            content_type: MIME type.
            bucket:       Override the default bucket.

        Returns:
            The stored *object_name*.
        """
        target_bucket = bucket or self.bucket
        client = self._client()

        if isinstance(data, bytes):
            stream: BinaryIO = io.BytesIO(data)
            length = len(data)
        else:
            stream = data
            length = -1  # unknown; MinIO will use chunked upload

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: client.put_object(
                target_bucket,
                object_name,
                stream,
                length=length,
                content_type=content_type,
            ),
        )
        logger.info(
            "Object uploaded",
            bucket=target_bucket,
            object_name=object_name,
            content_type=content_type,
        )
        return object_name

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(
        self, object_name: str, bucket: str | None = None
    ) -> None:
        """Remove an object from the bucket."""
        target_bucket = bucket or self.bucket
        client = self._client()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: client.remove_object(target_bucket, object_name),
        )
        logger.info("Object deleted", bucket=target_bucket, object_name=object_name)

    # ------------------------------------------------------------------
    # Pre-signed URL
    # ------------------------------------------------------------------

    async def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
        bucket: str | None = None,
    ) -> str:
        """
        Generate a pre-signed GET URL valid for *expires*.

        Args:
            object_name: The object path inside the bucket.
            expires:     Validity window (default: 1 hour).
            bucket:      Override the default bucket.

        Returns:
            A pre-signed URL string.
        """
        target_bucket = bucket or self.bucket
        client = self._client()

        loop = asyncio.get_event_loop()
        url: str = await loop.run_in_executor(
            None,
            lambda: client.presigned_get_object(
                target_bucket, object_name, expires=expires
            ),
        )
        return url

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """Verify MinIO connectivity by listing buckets."""
        start = time.monotonic()
        try:
            client = self._client()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: list(client.list_buckets()))
            latency = round((time.monotonic() - start) * 1000, 2)
            return {"status": "ok", "latency_ms": latency}
        except S3Error as exc:
            logger.error("MinIO health check failed", error=str(exc))
            return {"status": "error", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.error("MinIO health check failed", error=str(exc))
            return {"status": "error", "error": str(exc)}


# Module-level default instance
storage_service = StorageService()
