"""流程图文档持久化、Mermaid 编译和语义导出。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote
from uuid import UUID

import uuid_utils
from loguru import logger
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.exceptions.business import BusinessException
from app.models.document import FlowchartDocument
from app.models.event import FlowchartEvent
from app.models.file import FlowchartFile
from app.models.provider_call import FlowchartProviderCall
from app.models.task import FlowchartTask
from app.schemas.diagram import DiagramDocument, DiagramSaveRequest
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentSaveResponse,
    FlowchartDocumentHistoryItem,
    FlowchartDocumentHistoryPage,
    FlowchartDocumentResponse,
    MermaidCompilation,
    MermaidCompilationState,
)
from app.schemas.export import ExportFormat, ExportRequest, ExportTaskResponse
from app.schemas.task import TERMINAL_TASK_STATUSES, TaskStatus, TaskType
from app.services.diagram_service import compile_mermaid
from app.services.object_storage import ObjectStorage, ObjectStorageError, get_object_storage


DOCUMENT_RETENTION = timedelta(days=30)
EXPORT_RETENTION = timedelta(hours=24)
EXPORT_TASK_RETENTION = timedelta(days=7)
MERMAID_COMPILATION_EVENT = "document_mermaid_compilation"
MERMAID_COMPILATION_ERROR_CODE = "MERMAID_RENDER_FAILED"
MERMAID_COMPILATION_ERROR_MESSAGE = "Mermaid 编译失败，请稍后重试"
EXPORT_READY_STAGE = "导出文件已生成"
EXPORT_WAITING_STAGE = "等待导出渲染"

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class DocumentVersionConflict(Exception):
    def __init__(self, document: FlowchartDocumentResponse) -> None:
        super().__init__("文档版本已更新，请加载最新内容")
        self.document = document


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _to_uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


async def _get_owned_document(
    session: AsyncSession,
    user_id: str,
    document_id: UUID,
    *,
    for_update: bool = False,
) -> FlowchartDocument:
    statement = select(FlowchartDocument).where(FlowchartDocument.id == document_id)
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    document = result.scalar_one_or_none()
    if document is None:
        raise BusinessException(code=404, message="流程图文档不存在")
    if document.user_id != user_id:
        raise BusinessException(code=403, message="无权访问该流程图文档")
    return document


def _document_payload(document: FlowchartDocument) -> dict[str, Any]:
    payload = dict(document.diagram_data or {})
    metadata = dict(payload.get("metadata") or {})
    metadata["version"] = document.version
    if document.source_task_id is not None:
        metadata.setdefault("sourceTaskId", str(document.source_task_id))
    payload["metadata"] = metadata
    return payload


async def get_mermaid_compilation(
    session: AsyncSession,
    document: FlowchartDocument,
) -> MermaidCompilation:
    result = await session.execute(
        select(FlowchartEvent)
        .where(
            FlowchartEvent.document_id == document.id,
            FlowchartEvent.event_name == MERMAID_COMPILATION_EVENT,
        )
        .order_by(FlowchartEvent.created_at.desc(), FlowchartEvent.id.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    payload = event.payload if event is not None and isinstance(event.payload, Mapping) else {}
    if payload.get("version") == document.version:
        try:
            status = MermaidCompilationState(str(payload.get("status")))
        except ValueError:
            status = MermaidCompilationState.IDLE
        if status is not MermaidCompilationState.IDLE:
            return MermaidCompilation(
                version=document.version,
                status=status,
                error_code=(
                    MERMAID_COMPILATION_ERROR_CODE
                    if status is MermaidCompilationState.FAILED
                    else None
                ),
                error_message=(
                    MERMAID_COMPILATION_ERROR_MESSAGE
                    if status is MermaidCompilationState.FAILED
                    else None
                ),
            )
    return MermaidCompilation(
        version=document.version,
        status=(
            MermaidCompilationState.READY
            if document.mermaid_source
            else MermaidCompilationState.IDLE
        ),
    )


async def to_document_response(
    session: AsyncSession,
    document: FlowchartDocument,
) -> FlowchartDocumentResponse:
    payload = _document_payload(document)
    payload.update(
        {
            "id": str(document.id),
            "mermaidSource": document.mermaid_source,
            "mermaidCompilation": (
                await get_mermaid_compilation(session, document)
            ).model_dump(mode="json", by_alias=True),
        }
    )
    return FlowchartDocumentResponse.model_validate(payload)


async def get_document(
    session: AsyncSession,
    user_id: str,
    document_id: UUID,
) -> FlowchartDocumentResponse:
    document = await _get_owned_document(session, user_id, document_id)
    return await to_document_response(session, document)


async def list_documents(
    session: AsyncSession,
    user_id: str,
    *,
    offset: int = 0,
    limit: int = 20,
    now: datetime | None = None,
) -> FlowchartDocumentHistoryPage:
    """返回当前用户仍在保留期内的成功生成文档摘要。"""

    result = await session.execute(
        select(FlowchartDocument)
        .where(
            FlowchartDocument.user_id == user_id,
            FlowchartDocument.source_task_id.is_not(None),
            FlowchartDocument.expires_at > (now or _utcnow()),
        )
        .order_by(FlowchartDocument.updated_at.desc(), FlowchartDocument.id.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    documents = result.scalars().all()
    has_more = len(documents) > limit
    return FlowchartDocumentHistoryPage(
        records=[
            FlowchartDocumentHistoryItem.model_validate(document)
            for document in documents[:limit]
        ],
        offset=offset,
        limit=limit,
        has_more=has_more,
    )


async def delete_document(
    session: AsyncSession,
    user_id: str,
    document_id: UUID,
    *,
    storage: ObjectStorage | None = None,
) -> DocumentDeleteResponse:
    """永久删除文档及其在本系统内的关联记录和导出对象。"""

    document = await _get_owned_document(
        session,
        user_id,
        document_id,
        for_update=True,
    )
    normalized_document_id = _to_uuid(document.id)

    task_conditions = [FlowchartTask.document_id == normalized_document_id]
    if document.source_task_id is not None:
        task_conditions.append(FlowchartTask.id == _to_uuid(document.source_task_id))
    task_result = await session.execute(
        select(FlowchartTask).where(
            FlowchartTask.user_id == user_id,
            or_(*task_conditions),
        )
    )
    tasks = task_result.scalars().all()
    terminal_statuses = {status.value for status in TERMINAL_TASK_STATUSES}
    if any(
        task.type == TaskType.DIAGRAM_EXPORT.value
        and task.status not in terminal_statuses
        for task in tasks
    ):
        await session.rollback()
        raise BusinessException(
            code=409,
            message="存在未完成的导出任务，暂时不能删除流程图",
            error_code="DOCUMENT_DELETE_BLOCKED",
        )

    task_ids = [_to_uuid(task.id) for task in tasks]
    event_conditions = [FlowchartEvent.document_id == normalized_document_id]
    file_conditions = [FlowchartFile.document_id == normalized_document_id]
    if task_ids:
        event_conditions.append(FlowchartEvent.task_id.in_(task_ids))
        file_conditions.append(FlowchartFile.task_id.in_(task_ids))

    event_result = await session.execute(
        select(FlowchartEvent).where(or_(*event_conditions))
    )
    events = event_result.scalars().all()

    provider_calls: list[FlowchartProviderCall] = []
    if task_ids:
        provider_call_result = await session.execute(
            select(FlowchartProviderCall).where(
                FlowchartProviderCall.task_id.in_(task_ids)
            )
        )
        provider_calls = provider_call_result.scalars().all()

    file_result = await session.execute(
        select(FlowchartFile).where(
            FlowchartFile.user_id == user_id,
            or_(*file_conditions),
        )
    )
    files = file_result.scalars().all()

    current_storage = storage or get_object_storage()
    try:
        for file in files:
            if file.stored_path and await current_storage.remove(file.stored_path) is False:
                raise ObjectStorageError("导出对象删除失败")
    except Exception:
        await session.rollback()
        raise BusinessException(
            code=503,
            message="流程图关联导出文件暂时无法删除，请稍后重试",
            error_code="DOCUMENT_DELETE_STORAGE_FAILED",
        ) from None

    try:
        for event in events:
            await session.delete(event)
        for provider_call in provider_calls:
            await session.delete(provider_call)
        for file in files:
            await session.delete(file)
        for task in tasks:
            await session.delete(task)
        await session.delete(document)
        await session.commit()
    except Exception:
        await session.rollback()
        raise BusinessException(
            code=503,
            message="流程图暂时无法删除，请稍后重试",
            error_code="DOCUMENT_DELETE_FAILED",
        ) from None

    return DocumentDeleteResponse(document_id=normalized_document_id)


def _save_payload(document: FlowchartDocument, request: DiagramSaveRequest, version: int) -> dict[str, Any]:
    payload = request.model_dump(mode="json", by_alias=True, exclude={"version"})
    existing_metadata = dict((document.diagram_data or {}).get("metadata") or {})
    existing_metadata["version"] = version
    if document.source_task_id is not None:
        existing_metadata.setdefault("sourceTaskId", str(document.source_task_id))
    payload["metadata"] = existing_metadata
    return payload


def _record_mermaid_compilation(
    session: AsyncSession,
    document: FlowchartDocument,
    *,
    version: int,
    status: MermaidCompilationState,
) -> None:
    session.add(
        FlowchartEvent(
            id=uuid_utils.uuid7(),
            user_id=document.user_id,
            event_name=MERMAID_COMPILATION_EVENT,
            document_id=_to_uuid(document.id),
            payload={"version": version, "status": status.value},
        )
    )


def _dispatch_compilation(
    scheduler: Callable[[UUID, int], None] | None,
    document_id: UUID,
    version: int,
) -> None:
    if scheduler is None:
        return
    try:
        scheduler(document_id, version)
    except Exception:
        # 保存事务已成功，后台编译可由手动重试或 Worker 恢复处理。
        logger.warning("flowchart Mermaid compile dispatch deferred documentId={}", document_id)


async def save_document(
    session: AsyncSession,
    user_id: str,
    document_id: UUID,
    request: DiagramSaveRequest,
    *,
    schedule_compilation: Callable[[UUID, int], None] | None = None,
) -> DocumentSaveResponse:
    document = await _get_owned_document(session, user_id, document_id)
    if document.version != request.version:
        raise DocumentVersionConflict(await to_document_response(session, document))

    next_version = document.version + 1
    payload = _save_payload(document, request, next_version)
    result = await session.execute(
        update(FlowchartDocument)
        .where(
            FlowchartDocument.id == document_id,
            FlowchartDocument.user_id == user_id,
            FlowchartDocument.version == request.version,
        )
        .values(
            title=request.title,
            direction=request.direction.value,
            diagram_data=payload,
            version=next_version,
            updated_at=_utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.rollback()
        latest = await _get_owned_document(session, user_id, document_id)
        raise DocumentVersionConflict(await to_document_response(session, latest))

    _record_mermaid_compilation(
        session,
        document,
        version=next_version,
        status=MermaidCompilationState.COMPILING,
    )
    await session.commit()
    _dispatch_compilation(schedule_compilation, _to_uuid(document.id), next_version)
    compilation = MermaidCompilation(
        version=next_version,
        status=MermaidCompilationState.COMPILING,
    )
    return DocumentSaveResponse(
        document_id=_to_uuid(document.id),
        version=next_version,
        mermaid_source=document.mermaid_source,
        mermaid_compilation=compilation,
    )


async def compile_document_mermaid(
    document_id: UUID,
    version: int,
    *,
    session_factory=None,
) -> None:
    factory = session_factory or get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(FlowchartDocument)
            .where(FlowchartDocument.id == document_id)
            .with_for_update()
        )
        document = result.scalar_one_or_none()
        if document is None or document.version != version:
            return
        payload = _document_payload(document)

    try:
        mermaid_source = compile_mermaid(payload)
    except asyncio.CancelledError:
        raise
    except Exception:
        await _finish_mermaid_compilation(
            document_id,
            version,
            status=MermaidCompilationState.FAILED,
            session_factory=factory,
        )
        return

    await _finish_mermaid_compilation(
        document_id,
        version,
        status=MermaidCompilationState.READY,
        mermaid_source=mermaid_source,
        session_factory=factory,
    )


async def _finish_mermaid_compilation(
    document_id: UUID,
    version: int,
    *,
    status: MermaidCompilationState,
    mermaid_source: str | None = None,
    session_factory,
) -> None:
    async with session_factory() as session:
        result = await session.execute(
            select(FlowchartDocument)
            .where(FlowchartDocument.id == document_id)
            .with_for_update()
        )
        document = result.scalar_one_or_none()
        if document is None or document.version != version:
            return
        if status is MermaidCompilationState.READY and mermaid_source is not None:
            document.mermaid_source = mermaid_source
        _record_mermaid_compilation(session, document, version=version, status=status)
        await session.commit()


def create_generated_document(
    task: FlowchartTask,
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> FlowchartDocument:
    """将已经过模型校验和 Mermaid 编译的任务结果落为首个文档版本。"""

    generated = DiagramDocument.model_validate(payload)
    diagram_data = generated.model_dump(
        mode="json",
        by_alias=True,
        exclude={"id", "mermaid_source"},
    )
    metadata = dict(diagram_data.get("metadata") or {})
    metadata["version"] = 1
    metadata.setdefault("sourceTaskId", str(task.id))
    diagram_data["metadata"] = metadata
    created_at = now or _utcnow()
    return FlowchartDocument(
        id=uuid_utils.uuid7(),
        user_id=task.user_id,
        title=generated.title,
        direction=generated.direction.value,
        diagram_data=diagram_data,
        mermaid_source=generated.mermaid_source,
        version=1,
        source_task_id=_to_uuid(task.id),
        expires_at=created_at + DOCUMENT_RETENTION,
    )


def sanitize_export_filename(title: str, extension: str) -> str:
    stem = title.replace("/", "").replace("\\", "")
    stem = _UNSAFE_FILENAME_CHARS.sub("_", stem).strip(" .")
    reserved_base = stem.split(".", 1)[0].upper()
    if not stem or reserved_base in _WINDOWS_RESERVED_NAMES:
        stem = "flowchart"
    return f"{stem[:100]}.{extension}"


async def create_document_export(
    session: AsyncSession,
    user_id: str,
    document_id: UUID,
    request: ExportRequest,
    *,
    storage: ObjectStorage | None = None,
    schedule_render: Callable[[UUID], None] | None = None,
) -> ExportTaskResponse:
    document = await _get_owned_document(session, user_id, document_id, for_update=True)
    export_format = request.format
    if export_format in {ExportFormat.SVG, ExportFormat.PNG}:
        # 渲染是独立的 Chromium Worker 工作，必须由 API/Worker 调度器提交。
        # 直接调用服务且未提供调度器时拒绝，避免返回一个永远不会执行的任务。
        if schedule_render is None:
            raise BusinessException(
                code=400,
                message="当前导出 Worker 尚未配置",
                error_code="EXPORT_FORMAT_UNSUPPORTED",
            )
        now = _utcnow()
        snapshot = _document_payload(document)
        task = FlowchartTask(
            id=uuid_utils.uuid7(),
            user_id=user_id,
            type=TaskType.DIAGRAM_EXPORT.value,
            status=TaskStatus.WAITING.value,
            progress=5,
            stage=EXPORT_WAITING_STAGE,
            request_snapshot={
                "documentId": str(document.id),
                "version": document.version,
                "title": document.title,
                "diagramData": snapshot,
                "mermaidSource": document.mermaid_source,
                "format": export_format.value,
                "background": request.background.value,
            },
            result={
                "documentId": str(document.id),
                "version": document.version,
                "format": export_format.value,
                "costPoints": 0,
            },
            document_id=_to_uuid(document.id),
            idempotency_key=str(uuid_utils.uuid7()),
            expires_at=now + EXPORT_TASK_RETENTION,
        )
        session.add(task)
        await session.commit()
        _dispatch_export(schedule_render, _to_uuid(task.id))
        return ExportTaskResponse(task_id=_to_uuid(task.id), status=TaskStatus.WAITING)

    if export_format not in {ExportFormat.MERMAID, ExportFormat.JSON}:
        raise BusinessException(
            code=400,
            message="当前仅支持 Mermaid 和 JSON 语义导出",
            error_code="EXPORT_FORMAT_UNSUPPORTED",
        )

    if export_format is ExportFormat.MERMAID:
        compilation = await get_mermaid_compilation(session, document)
        if compilation.status is not MermaidCompilationState.READY:
            raise BusinessException(
                code=409,
                message="当前版本的 Mermaid 尚未准备完成",
                error_code=MERMAID_COMPILATION_ERROR_CODE,
            )
        extension = "mmd"
        mime_type = "text/plain; charset=utf-8"
        content = document.mermaid_source.encode("utf-8")
    else:
        extension = "json"
        mime_type = "application/json"
        response = await to_document_response(session, document)
        content = json.dumps(
            response.model_dump(
                mode="json",
                by_alias=True,
                exclude={"mermaid_compilation"},
            ),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

    now = _utcnow()
    file = FlowchartFile(
        id=uuid_utils.uuid7(),
        user_id=user_id,
        document_id=_to_uuid(document.id),
        original_name=sanitize_export_filename(document.title, extension),
        stored_path="",
        file_size=len(content),
        mime_type=mime_type,
        format=export_format.value,
        file_role="export",
        expires_at=now + EXPORT_RETENTION,
    )
    # 路径完全由服务端派生；对本地无认证模式的用户标识也进行编码，避免其改变对象层级。
    storage_user_id = quote(user_id, safe="")
    file.stored_path = (
        f"export/{now:%Y%m%d}/{storage_user_id}/{document.id}/{file.id}.{extension}"
    )
    task = FlowchartTask(
        id=uuid_utils.uuid7(),
        user_id=user_id,
        type=TaskType.DIAGRAM_EXPORT.value,
        status=TaskStatus.SUCCESS.value,
        progress=100,
        stage=EXPORT_READY_STAGE,
        request_snapshot={
            "documentId": str(document.id),
            "version": document.version,
            "format": export_format.value,
            "background": request.background.value,
        },
        result={
            "documentId": str(document.id),
            "version": document.version,
            "format": export_format.value,
        },
        document_id=_to_uuid(document.id),
        output_file_id=_to_uuid(file.id),
        idempotency_key=str(uuid_utils.uuid7()),
        expires_at=now + EXPORT_TASK_RETENTION,
    )
    file.task_id = _to_uuid(task.id)
    current_storage = storage or get_object_storage()
    try:
        await current_storage.put_bytes(
            file.stored_path,
            content,
            content_type=mime_type,
        )
    except (ObjectStorageError, OSError):
        raise BusinessException(
            code=503,
            message="导出文件暂时无法写入，请稍后重试",
            error_code="EXPORT_RENDER_FAILED",
        ) from None

    session.add(file)
    session.add(task)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        await current_storage.remove(file.stored_path)
        raise
    return ExportTaskResponse(task_id=_to_uuid(task.id), status=TaskStatus.SUCCESS)


def _dispatch_export(scheduler: Callable[[UUID], None] | None, task_id: UUID) -> None:
    if scheduler is None:
        return
    try:
        scheduler(task_id)
    except Exception:
        logger.warning("flowchart export dispatch deferred taskId={}", task_id)


__all__ = [
    "DOCUMENT_RETENTION",
    "EXPORT_RETENTION",
    "EXPORT_TASK_RETENTION",
    "EXPORT_WAITING_STAGE",
    "MERMAID_COMPILATION_EVENT",
    "DocumentVersionConflict",
    "compile_document_mermaid",
    "create_document_export",
    "create_generated_document",
    "delete_document",
    "get_document",
    "get_mermaid_compilation",
    "list_documents",
    "sanitize_export_filename",
    "save_document",
    "to_document_response",
]
