"""SVG/PNG 导出任务的 Worker 编排。"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID

import uuid_utils
from loguru import logger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.exceptions.business import BusinessException
from app.models.file import FlowchartFile
from app.models.task import FlowchartTask
from app.schemas.export import ExportBackground, ExportFormat
from app.schemas.task import TaskStatus, TaskType
from app.services.document_service import (
    EXPORT_RETENTION,
    sanitize_export_filename,
)
from app.services.event_service import publish_task_event, task_status_event_from_task
from app.services.export_renderer import (
    ExportRenderError,
    ExportRenderer,
    get_export_renderer,
    is_valid_rendered_content,
)
from app.services.object_storage import ObjectStorage, ObjectStorageError, get_object_storage


RENDERING_STAGE = "正在渲染导出文件"
EXPORT_SUCCESS_STAGE = "导出文件已生成"
EXPORT_FAILURE_STAGE = "导出失败"
EXPORT_REQUEUE_AFTER = timedelta(minutes=2)
EXPORT_MIME_TYPES = {
    ExportFormat.SVG: ("svg", "image/svg+xml"),
    ExportFormat.PNG: ("png", "image/png"),
}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def is_export_render_claimable(
    task: FlowchartTask,
    *,
    now: datetime | None = None,
) -> bool:
    """判断导出任务是否可以被 Worker 认领，避免重复渲染。

    ``rendering`` 任务只有在超过恢复窗口后才允许再次认领；这样 Beat
    可以恢复崩溃的 Worker，同时不会把正常进行中的渲染重复入队。
    """

    status = TaskStatus(task.status)
    if status is TaskStatus.WAITING:
        return True
    if status is not TaskStatus.RENDERING:
        return False
    updated_at = _as_naive_utc(getattr(task, "updated_at", None))
    if updated_at is None:
        # 单元测试构造的瞬态 ORM 对象没有 server_default；生产记录总有时间戳。
        return True
    current = _as_naive_utc(now) or _utcnow()
    return current - updated_at >= EXPORT_REQUEUE_AFTER


def _to_uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def download_url(file_id: UUID | str) -> str:
    return f"/api/flowchart/files/download?fileId={file_id}"


def _stored_path(user_id: str, document_id: UUID, file_id: UUID, extension: str, now: datetime) -> str:
    safe_user_id = quote(user_id, safe="")
    return f"export/{now:%Y%m%d}/{safe_user_id}/{document_id}/{file_id}.{extension}"


async def _load_export_task(session, task_id: UUID) -> FlowchartTask | None:
    result = await session.execute(
        select(FlowchartTask).where(FlowchartTask.id == task_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def _publish(task: FlowchartTask) -> None:
    try:
        await publish_task_event(task_status_event_from_task(task))
    except Exception:
        logger.warning("flowchart export event publish deferred taskId={}", task.id)


async def _mark_export_failed(
    task_id: UUID,
    *,
    session_factory,
    duration_ms: int,
) -> None:
    async with session_factory() as session:
        task = await _load_export_task(session, task_id)
        if (
            task is None
            or task.type != TaskType.DIAGRAM_EXPORT.value
            or TaskStatus(task.status) in {
                TaskStatus.SUCCESS,
                TaskStatus.FAILED,
                TaskStatus.CANCELED,
                TaskStatus.EXPIRED,
            }
        ):
            return
        task.status = TaskStatus.FAILED.value
        task.progress = 100
        task.stage = EXPORT_FAILURE_STAGE
        task.error_code = "EXPORT_RENDER_FAILED"
        task.error_message = "导出渲染失败，请稍后重试"
        task.render_duration_ms = duration_ms
        await session.commit()
        await _publish(task)


async def render_document_export(
    task_id: UUID,
    *,
    session_factory=None,
    storage: ObjectStorage | None = None,
    renderer: ExportRenderer | None = None,
) -> None:
    """执行一个已提交的 SVG/PNG 导出任务；PostgreSQL 是状态事实来源。"""

    factory = session_factory or get_session_factory()
    current_storage = storage or get_object_storage()
    current_renderer = renderer or get_export_renderer()
    started = time.monotonic()

    async with factory() as session:
        task = await _load_export_task(session, task_id)
        if task is None or task.type != TaskType.DIAGRAM_EXPORT.value:
            return
        if not is_export_render_claimable(task):
            return
        snapshot = dict(task.request_snapshot or {})
        try:
            export_format = ExportFormat(str(snapshot["format"]))
            background = ExportBackground(str(snapshot.get("background", ExportBackground.TRANSPARENT.value)))
            if export_format not in EXPORT_MIME_TYPES:
                raise ValueError("当前任务不是 SVG/PNG 导出")
        except (KeyError, ValueError):
            await session.rollback()
            await _mark_export_failed(
                task_id,
                session_factory=factory,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return
        task.status = TaskStatus.RENDERING.value
        task.progress = 50
        task.stage = RENDERING_STAGE
        await session.commit()

    await _publish(task)

    try:
        content = await current_renderer.render(snapshot, export_format, background)
        max_size = get_settings().export.max_file_size
        if len(content) > max_size or not is_valid_rendered_content(export_format, content):
            raise ExportRenderError("导出内容无效")
    except Exception:
        await _mark_export_failed(
            task_id,
            session_factory=factory,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return

    now = _utcnow()
    extension, mime_type = EXPORT_MIME_TYPES[export_format]
    uploaded_path: str | None = None
    try:
        async with factory() as session:
            task = await _load_export_task(session, task_id)
            if task is None or TaskStatus(task.status) in {
                TaskStatus.CANCELED,
                TaskStatus.EXPIRED,
                TaskStatus.SUCCESS,
                TaskStatus.FAILED,
            }:
                return
            snapshot = dict(task.request_snapshot or {})
            document_id = _to_uuid(snapshot["documentId"])
            file_id = _to_uuid(uuid_utils.uuid7())
            title = str(snapshot.get("title") or "flowchart")
            file = FlowchartFile(
                id=file_id,
                user_id=task.user_id,
                document_id=document_id,
                task_id=_to_uuid(task.id),
                original_name=sanitize_export_filename(title, extension),
                stored_path=_stored_path(task.user_id, document_id, file_id, extension, now),
                file_size=len(content),
                mime_type=mime_type,
                format=export_format.value,
                file_role="export",
                expires_at=now + EXPORT_RETENTION,
            )
            uploaded_path = file.stored_path
            await current_storage.put_bytes(uploaded_path, content, content_type=mime_type)
            file_id = _to_uuid(file.id)
            task.output_file_id = file_id
            task.status = TaskStatus.SUCCESS.value
            task.progress = 100
            task.stage = EXPORT_SUCCESS_STAGE
            task.result = {
                **dict(task.result or {}),
                "documentId": str(document_id),
                "version": snapshot.get("version"),
                "format": export_format.value,
                "downloadUrl": download_url(file_id),
                "costPoints": 0,
            }
            task.render_duration_ms = int((time.monotonic() - started) * 1000)
            session.add(file)
            await session.commit()
            await _publish(task)
    except (ObjectStorageError, OSError, KeyError, ValueError, BusinessException):
        if uploaded_path:
            try:
                await current_storage.remove(uploaded_path)
            except Exception:
                pass
        await _mark_export_failed(
            task_id,
            session_factory=factory,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception:
        if uploaded_path:
            try:
                await current_storage.remove(uploaded_path)
            except Exception:
                pass
        await _mark_export_failed(
            task_id,
            session_factory=factory,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


async def cleanup_expired_export_files(*, session_factory=None, storage: ObjectStorage | None = None) -> int:
    from app.services.file_service import cleanup_expired_files

    factory = session_factory or get_session_factory()
    async with factory() as session:
        return await cleanup_expired_files(session, storage=storage)


__all__ = [
    "EXPORT_MIME_TYPES",
    "EXPORT_FAILURE_STAGE",
    "EXPORT_REQUEUE_AFTER",
    "EXPORT_SUCCESS_STAGE",
    "RENDERING_STAGE",
    "cleanup_expired_export_files",
    "download_url",
    "is_export_render_claimable",
    "render_document_export",
]
