"""MinIO 对象存储适配器。"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from io import BytesIO
from typing import Protocol

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings


class ObjectStorage(Protocol):
    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        *,
        content_type: str,
    ) -> None: ...

    async def remove(self, object_name: str) -> bool: ...

    async def get_bytes(self, object_name: str) -> bytes: ...


class ObjectStorageError(RuntimeError):
    pass


class MinioObjectStorage:
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool,
        bucket: str,
    ) -> None:
        self._bucket = bucket
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    async def put_bytes(
        self,
        object_name: str,
        data: bytes,
        *,
        content_type: str,
    ) -> None:
        try:
            await asyncio.to_thread(
                self._put_bytes_sync,
                object_name,
                data,
                content_type,
            )
        except (OSError, S3Error) as exc:
            raise ObjectStorageError("对象存储暂不可用") from exc

    async def remove(self, object_name: str) -> bool:
        try:
            await asyncio.to_thread(self._client.remove_object, self._bucket, object_name)
            return True
        except (OSError, S3Error):
            # 调用方可据此决定是否保留数据库记录，供下次清理重试。
            return False

    async def get_bytes(self, object_name: str) -> bytes:
        try:
            return await asyncio.to_thread(self._get_bytes_sync, object_name)
        except (OSError, S3Error) as exc:
            raise ObjectStorageError("对象存储暂不可用") from exc

    def _put_bytes_sync(
        self,
        object_name: str,
        data: bytes,
        content_type: str,
    ) -> None:
        self._ensure_bucket()
        self._client.put_object(
            self._bucket,
            object_name,
            BytesIO(data),
            len(data),
            content_type=content_type,
        )

    def _ensure_bucket(self) -> None:
        if self._client.bucket_exists(self._bucket):
            return
        try:
            self._client.make_bucket(self._bucket)
        except S3Error as exc:
            if exc.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                raise

    def _get_bytes_sync(self, object_name: str) -> bytes:
        response = self._client.get_object(self._bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


@lru_cache(maxsize=1)
def get_object_storage() -> MinioObjectStorage:
    config = get_settings().minio
    return MinioObjectStorage(
        endpoint=config.endpoint,
        access_key=config.access_key,
        secret_key=config.secret_key,
        secure=config.secure,
        bucket=config.bucket,
    )
