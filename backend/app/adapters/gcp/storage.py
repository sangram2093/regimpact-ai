import asyncio
import re
from typing import Any

from app.domain.errors import DomainError


class GCSObjectStorage:
    """Bounded reads and immutable, retry-safe writes within one configured bucket."""

    def __init__(self, client: Any, bucket: str, *, max_bytes: int = 20 * 1024 * 1024) -> None:
        if not bucket or "/" in bucket or ":" in bucket:
            raise ValueError("A bucket name, not a URI, is required")
        self.client = client
        self.bucket_name = bucket
        self.max_bytes = max_bytes

    @classmethod
    def from_project(cls, project: str, bucket: str, **kwargs) -> "GCSObjectStorage":
        if not project:
            raise ValueError("An explicit Google Cloud project is required")
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise DomainError(
                "GCP_DEPENDENCY_MISSING", "Install backend cloud dependencies.", 503
            ) from exc
        return cls(storage.Client(project=project), bucket, **kwargs)

    @staticmethod
    def _key(key: str) -> str:
        if (
            not re.fullmatch(r"[A-Za-z0-9_./-]{1,512}", key)
            or key.startswith("/")
            or any(part in {"", ".", ".."} for part in key.split("/"))
        ):
            raise DomainError(
                "INVALID_OBJECT_KEY", "Use a relative, non-traversing object key.", 422
            )
        return key

    def _read(self, key: str) -> bytes:
        blob = self.client.bucket(self.bucket_name).blob(self._key(key))
        try:
            blob.reload(timeout=30)
            if blob.size is None or blob.size > self.max_bytes:
                raise DomainError("SOURCE_SIZE_LIMIT", "Stored source exceeds the size limit.", 413)
            data = blob.download_as_bytes(
                if_generation_match=blob.generation,
                raw_download=True,
                timeout=30,
                checksum="auto",
            )
            if len(data) > self.max_bytes:
                raise DomainError("SOURCE_SIZE_LIMIT", "Stored source exceeds the size limit.", 413)
            return data
        except DomainError:
            raise
        except Exception as exc:
            if getattr(exc, "code", None) == 404:
                raise DomainError(
                    "STORAGE_OBJECT_NOT_FOUND", "The configured source object does not exist.", 404
                ) from exc
            raise DomainError(
                "STORAGE_READ_FAILED", "Unable to read the configured source object.", 503
            ) from exc

    async def read(self, object_key: str) -> bytes:
        return await asyncio.to_thread(self._read, object_key)

    def _exists(self, key: str) -> bool:
        blob = self.client.bucket(self.bucket_name).blob(self._key(key))
        try:
            blob.reload(timeout=30)
            return blob.size is not None and 0 < blob.size <= self.max_bytes
        except Exception as exc:
            if getattr(exc, "code", None) == 404:
                return False
            raise DomainError(
                "STORAGE_READ_FAILED", "Unable to inspect the configured source object.", 503
            ) from exc

    async def exists(self, object_key: str) -> bool:
        """Metadata-only availability check; ingestion still verifies the actual bytes."""
        return await asyncio.to_thread(self._exists, object_key)

    def _write(self, key: str, content: bytes, content_type: str) -> str:
        key = self._key(key)
        if not content or len(content) > self.max_bytes:
            raise DomainError(
                "SOURCE_SIZE_LIMIT", "Stored content is empty or exceeds the size limit.", 413
            )
        if content_type not in {"application/pdf", "application/json"}:
            raise DomainError("UNSUPPORTED_SOURCE_TYPE", "Unsupported source object type.", 415)
        blob = self.client.bucket(self.bucket_name).blob(key)
        try:
            blob.upload_from_string(
                content,
                content_type=content_type,
                if_generation_match=0,
                timeout=30,
                checksum="auto",
            )
        except Exception as exc:
            # Google API errors expose code=412. A matching object is an idempotent retry;
            # an existing different object can never be overwritten by this adapter.
            if getattr(exc, "code", None) == 412:
                if self._read(key) != content:
                    raise DomainError(
                        "SOURCE_OBJECT_CONFLICT", "Source object already has different bytes.", 409
                    ) from exc
            else:
                raise DomainError(
                    "STORAGE_WRITE_FAILED", "Unable to store the source object.", 503
                ) from exc
        return f"gs://{self.bucket_name}/{key}"

    async def write(self, object_key: str, content: bytes, content_type: str) -> str:
        return await asyncio.to_thread(self._write, object_key, content, content_type)
