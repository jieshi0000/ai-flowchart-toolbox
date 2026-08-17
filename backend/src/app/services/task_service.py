"""第八天的本地流程图任务创建与查询服务。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import uuid_utils
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.business import BusinessException
from app.models.task import FlowchartTask
from app.providers.provider_registry import (
    ProviderRegistration,
    ProviderRegistry,
    ProviderSelectionError,
    get_provider_registry,
)
from app.schemas.provider import ProviderCapability
from app.schemas.task import (
    TERMINAL_TASK_STATUSES,
    TaskCancelResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskRetryResponse,
    TaskStatus,
    TaskStatusResponse,
)

TASK_RETENTION = timedelta(days=7)
WAITING_STAGE = "任务已创建，等待处理"
CANCELED_STAGE = "任务已取消"
CANCELLABLE_TASK_STATUSES = frozenset(
    {
        TaskStatus.WAITING,
        TaskStatus.SUBMITTING,
        TaskStatus.PROVIDER_QUEUED,
        TaskStatus.PROVIDER_PROCESSING,
    }
)
RETRYABLE_TASK_STATUSES = frozenset(
    {TaskStatus.FAILED, TaskStatus.CANCELED, TaskStatus.EXPIRED}
)
_PROVIDER_ERROR_HTTP_CODES = {
    "PROVIDER_NOT_CONFIGURED": 400,
    "PROVIDER_UNHEALTHY": 502,
    "PROVIDER_RATE_LIMITED": 429,
}


def _utcnow() -> datetime:
    """数据库使用无时区 TIMESTAMP，统一写入 UTC 时间。"""

    return datetime.now(UTC).replace(tzinfo=None)


async def _find_by_idempotency_key(
    session: AsyncSession,
    user_id: str,
    idempotency_key: str,
) -> FlowchartTask | None:
    result = await session.execute(
        select(FlowchartTask).where(
            FlowchartTask.user_id == user_id,
            FlowchartTask.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def _get_owned_task(
    session: AsyncSession,
    user_id: str,
    task_id: UUID,
) -> FlowchartTask:
    result = await session.execute(select(FlowchartTask).where(FlowchartTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise BusinessException(code=404, message="任务不存在")
    if task.user_id != user_id:
        raise BusinessException(code=403, message="无权访问该任务")
    return task


def _select_provider(
    request: TaskCreateRequest,
    registry: ProviderRegistry | None,
) -> ProviderRegistration:
    current = registry or get_provider_registry()
    try:
        return current.select(
            (
                ProviderCapability.TEXT_GENERATION,
                ProviderCapability.STRUCTURED_OUTPUT,
            ),
            provider_id=request.provider_id,
            model=request.model,
        )
    except ProviderSelectionError as exc:
        raise BusinessException(
            code=_PROVIDER_ERROR_HTTP_CODES.get(exc.code, 400),
            message=exc.message,
            error_code=exc.code,
        ) from exc


def _to_uuid(value: object) -> UUID:
    """兼容 uuid-utils 的 UUID v7 对象与 SQLAlchemy 读取出的标准 UUID。"""

    return value if isinstance(value, UUID) else UUID(str(value))


def _to_create_response(task: FlowchartTask) -> TaskCreateResponse:
    return TaskCreateResponse(
        task_id=_to_uuid(task.id),
        status=TaskStatus(task.status),
        estimated_seconds=30,
    )


def _to_status_response(task: FlowchartTask) -> TaskStatusResponse:
    return TaskStatusResponse(
        task_id=_to_uuid(task.id),
        type=task.type,
        status=task.status,
        progress=task.progress,
        stage=task.stage,
        provider_id=task.provider_id,
        model_name=task.model_name,
        poll_count=task.poll_count,
        document_id=_to_uuid(task.document_id) if task.document_id is not None else None,
        download_url=None,
        error_code=task.error_code,
        error_message=task.error_message,
    )


async def create_task(
    session: AsyncSession,
    user_id: str,
    request: TaskCreateRequest,
    *,
    registry: ProviderRegistry | None = None,
    source_task_id: UUID | None = None,
) -> TaskCreateResponse:
    """创建本地任务；重复幂等键复用已有任务，不发起供应商调用。"""

    existing = await _find_by_idempotency_key(session, user_id, request.idempotency_key)
    if existing is not None:
        return _to_create_response(existing)

    selected_provider = _select_provider(request, registry)
    now = _utcnow()
    request_snapshot = request.model_dump(mode="json", exclude={"idempotency_key"})
    if source_task_id is not None:
        request_snapshot["source_task_id"] = str(source_task_id)

    task = FlowchartTask(
        id=uuid_utils.uuid7(),
        user_id=user_id,
        type=request.type.value,
        status=TaskStatus.WAITING.value,
        progress=5,
        stage=WAITING_STAGE,
        request_snapshot=request_snapshot,
        provider_id=selected_provider.provider_id,
        model_name=selected_provider.config.model,
        idempotency_key=request.idempotency_key,
        deadline_at=now + timedelta(seconds=selected_provider.config.task_timeout_seconds),
        expires_at=now + TASK_RETENTION,
    )
    session.add(task)
    try:
        await session.commit()
    except IntegrityError:
        # 并发请求可能都通过了首次查询，由数据库唯一约束裁决并复用胜者。
        await session.rollback()
        existing = await _find_by_idempotency_key(session, user_id, request.idempotency_key)
        if existing is not None:
            return _to_create_response(existing)
        raise
    return _to_create_response(task)


async def get_task(
    session: AsyncSession,
    user_id: str,
    task_id: UUID,
) -> TaskStatusResponse:
    return _to_status_response(await _get_owned_task(session, user_id, task_id))


async def cancel_task(
    session: AsyncSession,
    user_id: str,
    task_id: UUID,
) -> TaskCancelResponse:
    task = await _get_owned_task(session, user_id, task_id)
    status = TaskStatus(task.status)
    if status in TERMINAL_TASK_STATUSES:
        raise BusinessException(
            code=409,
            message="任务已结束，不能取消",
            error_code="TASK_CANCELED" if status is TaskStatus.CANCELED else None,
        )
    if status not in CANCELLABLE_TASK_STATUSES:
        raise BusinessException(code=409, message="当前任务阶段不能取消")

    result = await session.execute(
        update(FlowchartTask)
        .where(
            FlowchartTask.id == task_id,
            FlowchartTask.user_id == user_id,
            FlowchartTask.status.in_([item.value for item in CANCELLABLE_TASK_STATUSES]),
        )
        .values(
            status=TaskStatus.CANCELED.value,
            stage=CANCELED_STAGE,
            error_code="TASK_CANCELED",
            error_message="任务已取消",
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.rollback()
        raise BusinessException(code=409, message="任务状态已变化，请刷新后重试")

    await session.commit()
    return TaskCancelResponse(
        task_id=_to_uuid(task.id),
        status=TaskStatus.CANCELED,
        # D09 才会在 Worker 中向已有供应商请求发出尽力取消。
        provider_cancel_requested=bool(task.provider_request_id),
    )


async def retry_task(
    session: AsyncSession,
    user_id: str,
    task_id: UUID,
    *,
    registry: ProviderRegistry | None = None,
) -> TaskRetryResponse:
    source_task = await _get_owned_task(session, user_id, task_id)
    if TaskStatus(source_task.status) not in RETRYABLE_TASK_STATUSES:
        raise BusinessException(code=409, message="仅失败、已取消或已过期的任务可以重试")

    snapshot = source_task.request_snapshot
    try:
        request = TaskCreateRequest(
            type=snapshot["type"],
            prompt=snapshot["prompt"],
            direction=snapshot.get("direction", "TB"),
            detail_level=snapshot.get("detail_level", "standard"),
            provider_id=snapshot.get("provider_id"),
            model=snapshot.get("model"),
            idempotency_key=str(uuid_utils.uuid7()),
        )
    except (KeyError, ValidationError) as exc:
        raise BusinessException(code=409, message="原任务请求快照无效，无法重试") from exc

    created = await create_task(
        session,
        user_id,
        request,
        registry=registry,
        source_task_id=source_task.id,
    )
    return TaskRetryResponse(
        task_id=created.task_id,
        source_task_id=_to_uuid(source_task.id),
        status=created.status,
    )


__all__ = [
    "CANCELLABLE_TASK_STATUSES",
    "RETRYABLE_TASK_STATUSES",
    "cancel_task",
    "create_task",
    "get_task",
    "retry_task",
]
