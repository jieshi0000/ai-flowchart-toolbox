"""导出文件的归属校验、下载和到期清理。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.business import BusinessException
from app.models.file import FlowchartFile
from app.services.object_storage import ObjectStorage, ObjectStorageError, get_object_storage


@dataclass(frozen=True)
class FileDownload:
    content: bytes
    filename: str
    mime_type: str


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _normalize_now(value: datetime | None) -> datetime:
    if value is None:
        return _utcnow()
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


async def _get_file(
    session: AsyncSession,
    user_id: str,
    file_id: UUID,
    *,
    for_update: bool = False,
) -> FlowchartFile:
    statement = select(FlowchartFile).where(FlowchartFile.id == file_id)
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    file = result.scalar_one_or_none()
    if file is None:
        raise BusinessException(code=404, message="导出文件不存在")
    if file.user_id != user_id:
        raise BusinessException(code=403, message="无权下载该导出文件")
    if file.file_role != "export":
        raise BusinessException(code=404, message="导出文件不存在")
    return file


async def download_file(
    session: AsyncSession,
    user_id: str,
    file_id: UUID,
    *,
    storage: ObjectStorage | None = None,
    now: datetime | None = None,
) -> FileDownload:
    file = await _get_file(session, user_id, file_id)
    if _normalize_now(file.expires_at) <= _normalize_now(now):
        # 记录过期后尽力删除对象和数据库条目；下载请求仍返回明确的 404。
        current_storage = storage or get_object_storage()
        removed = False
        try:
            removed = await current_storage.remove(file.stored_path) is not False
        except Exception:
            removed = False
        if removed:
            await session.delete(file)
            await session.commit()
        raise BusinessException(code=404, message="导出文件已过期", error_code="EXPORT_FILE_EXPIRED")

    current_storage = storage or get_object_storage()
    try:
        content = await current_storage.get_bytes(file.stored_path)
    except (ObjectStorageError, OSError):
        raise BusinessException(
            code=503,
            message="导出文件暂时无法读取，请稍后重试",
            error_code="EXPORT_FILE_UNAVAILABLE",
        ) from None
    return FileDownload(content=content, filename=file.original_name, mime_type=file.mime_type)


async def cleanup_expired_files(
    session: AsyncSession,
    *,
    storage: ObjectStorage | None = None,
    now: datetime | None = None,
) -> int:
    """删除已经过期的对象和记录；对象删除失败时保留记录供下次重试。"""

    result = await session.execute(
        select(FlowchartFile)
        .where(
            FlowchartFile.file_role == "export",
            FlowchartFile.expires_at <= _normalize_now(now),
        )
        .order_by(FlowchartFile.expires_at)
    )
    current_storage = storage or get_object_storage()
    removed_count = 0
    for file in result.scalars().all():
        try:
            delete_succeeded = await current_storage.remove(file.stored_path)
            if delete_succeeded is False:
                continue
        except Exception:
            continue
        await session.delete(file)
        removed_count += 1
    if removed_count:
        await session.commit()
    return removed_count


__all__ = ["FileDownload", "cleanup_expired_files", "download_file"]
