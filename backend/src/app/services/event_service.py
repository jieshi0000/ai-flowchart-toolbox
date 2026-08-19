"""Redis 任务事件发布与 SSE 流读取。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
import json
from typing import Any
from uuid import UUID

from loguru import logger
from redis.exceptions import RedisError

from app.core.redis import get_redis
from app.core.redis_keys import format_key
from app.models.task import FlowchartTask
from app.schemas.task import TERMINAL_TASK_STATUSES, TaskStatus, TaskStatusResponse
from app.schemas.task_event import TaskStatusEvent


TASK_STATUS_EVENT_NAME = "task-status"
TASK_EVENT_NAMESPACE = "flowchart-task-events"
TASK_EVENT_HEARTBEAT_SECONDS = 15.0
TaskEventRefresh = Callable[[], Awaitable[TaskStatusEvent]]
TaskEventPublisher = Callable[[TaskStatusEvent], Awaitable[None]]


def task_event_channel(task_id: UUID) -> str:
    """返回按应用命名空间隔离的 Redis Pub/Sub channel。"""

    return format_key(TASK_EVENT_NAMESPACE, str(task_id))


def task_status_event_from_task(task: FlowchartTask) -> TaskStatusEvent:
    download_url = (
        f"/api/flowchart/files/download?fileId={task.output_file_id}"
        if task.output_file_id is not None
        else None
    )
    return TaskStatusEvent(
        task_id=_to_uuid(task.id),
        type=task.type,
        status=TaskStatus(task.status),
        progress=task.progress,
        stage=task.stage,
        document_id=_to_uuid(task.document_id) if task.document_id is not None else None,
        download_url=download_url,
        error_code=task.error_code,
        error_message=task.error_message,
    )


def task_status_event_from_response(response: TaskStatusResponse) -> TaskStatusEvent:
    return TaskStatusEvent(
        task_id=response.task_id,
        type=response.type,
        status=response.status,
        progress=response.progress,
        stage=response.stage,
        document_id=response.document_id,
        download_url=response.download_url,
        error_code=response.error_code,
        error_message=response.error_message,
    )


async def publish_task_event(
    event: TaskStatusEvent,
    *,
    redis_client: Any | None = None,
) -> None:
    """发布状态事件；Redis 短暂不可用时不影响任务状态机。"""

    client = redis_client or get_redis()
    payload = event.model_dump_json(by_alias=True, exclude_none=True)
    try:
        await client.publish(task_event_channel(event.task_id), payload)
    except (RedisError, OSError, asyncio.TimeoutError):
        # PostgreSQL 是任务事实来源，SSE 断开后客户端会轮询恢复状态。
        logger.warning("flowchart task event publish deferred taskId={}", event.task_id)


@asynccontextmanager
async def subscribe_task_events(
    task_id: UUID,
    *,
    redis_client: Any | None = None,
) -> AsyncIterator[Any]:
    """订阅单个任务的 Redis channel，并在离开时释放 Pub/Sub 连接。"""

    client = redis_client or get_redis()
    pubsub = None
    channel = task_event_channel(task_id)
    try:
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        yield pubsub
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(channel)
            except (RedisError, OSError, asyncio.TimeoutError):
                pass
            try:
                await pubsub.aclose()
            except (RedisError, OSError, asyncio.TimeoutError):
                pass


async def stream_task_events(
    task_id: UUID,
    initial_event: TaskStatusEvent,
    *,
    refresh: TaskEventRefresh | None = None,
    redis_client: Any | None = None,
) -> AsyncIterator[str]:
    """生成 SSE 文本；终态事件发送后立即结束监听。"""

    if initial_event.status in TERMINAL_TASK_STATUSES:
        yield encode_sse_event(initial_event)
        return

    try:
        async with subscribe_task_events(task_id, redis_client=redis_client) as pubsub:
            current = initial_event
            if refresh is not None:
                try:
                    # 订阅建立后再刷新一次，缩小查询与订阅之间的竞态窗口。
                    current = await refresh()
                except Exception:
                    current = initial_event
            yield encode_sse_event(current)
            if current.status in TERMINAL_TASK_STATUSES:
                return

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=TASK_EVENT_HEARTBEAT_SECONDS,
                )
                if message is None:
                    # 注释帧只用于保持代理连接，不会被前端当作任务事件。
                    yield ": keep-alive\n\n"
                    continue
                if message.get("type") != "message":
                    continue
                event = decode_task_event(message.get("data"))
                if event is None:
                    continue
                yield encode_sse_event(event)
                if event.status in TERMINAL_TASK_STATUSES:
                    return
    except asyncio.CancelledError:
        raise
    except (RedisError, OSError, asyncio.TimeoutError):
        # 客户端看到流结束后切换到 GET 轮询；不把 Redis 连接信息写入响应。
        logger.warning("flowchart task event stream unavailable taskId={}", task_id)


def encode_sse_event(event: TaskStatusEvent) -> str:
    payload = event.model_dump(mode="json", by_alias=True, exclude_none=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {TASK_STATUS_EVENT_NAME}\ndata: {data}\n\n"


def decode_task_event(value: Any) -> TaskStatusEvent | None:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        return None
    try:
        return TaskStatusEvent.model_validate_json(value)
    except (TypeError, ValueError):
        return None


def _to_uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


__all__ = [
    "TASK_EVENT_HEARTBEAT_SECONDS",
    "TASK_STATUS_EVENT_NAME",
    "TaskEventPublisher",
    "TaskStatusEvent",
    "decode_task_event",
    "encode_sse_event",
    "publish_task_event",
    "stream_task_events",
    "subscribe_task_events",
    "task_event_channel",
    "task_status_event_from_response",
    "task_status_event_from_task",
]
