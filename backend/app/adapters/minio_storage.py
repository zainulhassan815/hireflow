"""MinIO / S3-compatible blob storage adapter.

Uses the synchronous `minio` SDK wrapped in `asyncio.to_thread` so the async
interface doesn't block the event loop. The minio SDK is well-tested and
purpose-built for MinIO; switching to real S3 is just an endpoint change.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from io import BytesIO

from minio import Minio
from pydantic import SecretStr

from app.adapters.protocols import StoredBlob


class MinioBlobStorage:
    """`BlobStorage` protocol implementation backed by MinIO."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: SecretStr,
        bucket: str,
        region: str = "us-east-1",
        secure: bool = False,
    ) -> None:
        clean_endpoint = endpoint.replace("http://", "").replace("https://", "")
        secure = endpoint.startswith("https://")
        self._bucket = bucket
        self._client = Minio(
            clean_endpoint,
            access_key=access_key,
            secret_key=secret_key.get_secret_value(),
            region=region,
            secure=secure,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> StoredBlob:
        result = await asyncio.to_thread(
            self._client.put_object,
            self._bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return StoredBlob(
            key=key,
            size=len(data),
            etag=result.etag.strip('"'),
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, self._bucket, key)
        try:
            return await asyncio.to_thread(response.read)
        finally:
            await asyncio.to_thread(response.close)
            await asyncio.to_thread(response.release_conn)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.remove_object, self._bucket, key)

    async def presigned_url(self, key: str, expires_seconds: int = 3600) -> str:
        return await asyncio.to_thread(
            self._client.presigned_get_object,
            self._bucket,
            key,
            expires=timedelta(seconds=expires_seconds),
        )

    def get_sync(self, key: str) -> bytes:
        """Synchronous variant for use in Celery workers."""
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def put_sync(self, key: str, data: bytes, content_type: str) -> StoredBlob:
        """Synchronous variant for use in Celery workers."""
        result = self._client.put_object(
            self._bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return StoredBlob(
            key=key,
            size=len(data),
            etag=result.etag.strip('"'),
        )
