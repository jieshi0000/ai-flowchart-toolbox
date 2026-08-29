"""流程图异步任务的状态机和供应商编排。

Celery 只负责触发本模块的协程。任务状态、结果和补偿依据始终保存在
PostgreSQL，避免把 Redis 队列状态当成业务事实。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import uuid_utils
from loguru import logger
from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.models.provider_call import FlowchartProviderCall
from app.models.task import FlowchartTask
from app.providers.base import ProviderPollResult, ProviderSubmission
from app.providers.provider_registry import (
    ProviderRegistration,
    ProviderRegistry,
    ProviderSelectionError,
    get_provider_registry,
)
from app.providers.transport import ProviderTransportError
from app.schemas.task import TERMINAL_TASK_STATUSES, TaskStatus, TaskType
from app.services.document_service import create_generated_document
from app.services.diagram_service import compile_generated_diagram_document
from app.services.event_service import (
    TaskEventPublisher,
    publish_task_event,
    task_status_event_from_task,
)
from app.services.export_service import is_export_render_claimable


POLL_BACKOFF_SECONDS = (3, 6, 12, 15, 15)
MIN_POLL_SECONDS = 3
MAX_POLL_SECONDS = 15
SUBMIT_WATCHDOG_SECONDS = 60
COMPENSATION_LIMIT = 100
# 任务在尚未获得供应商请求标识前最多等待一小时。超过该时间通常意味着
# Worker/消息投递已中断，继续补调度会让用户看到无期限的“处理中”。
ZOMBIE_SUBMISSION_TIMEOUT = timedelta(hours=1)

_DIAGRAM_THEME_STYLES: dict[str, dict[str, dict[str, str]]] = {
    "blue": {
        "start": {"fill": "#EEF5FF", "stroke": "#8EB8FF"},
        "end": {"fill": "#EDF3FF", "stroke": "#8EB8FF"},
        "process": {"fill": "#EEF5FF", "stroke": "#B9D2FF"},
        "decision": {"fill": "#FFF8E7", "stroke": "#E9C77A"},
        "input_output": {"fill": "#EEF7FB", "stroke": "#9CCFE5"},
        "subprocess": {"fill": "#F3F0FF", "stroke": "#C8BAF5"},
    },
    "purple": {
        "start": {"fill": "#F3F0FF", "stroke": "#B7A8F0"},
        "end": {"fill": "#F3F0FF", "stroke": "#B7A8F0"},
        "process": {"fill": "#F5F1FF", "stroke": "#D3C7FF"},
        "decision": {"fill": "#FFF8E7", "stroke": "#E9C77A"},
        "input_output": {"fill": "#F1F4FF", "stroke": "#B8C6F1"},
        "subprocess": {"fill": "#F7EFFF", "stroke": "#D9BDF5"},
    },
    "green": {
        "start": {"fill": "#EAFAF4", "stroke": "#8ED3B6"},
        "end": {"fill": "#EAFAF4", "stroke": "#8ED3B6"},
        "process": {"fill": "#EDFBF5", "stroke": "#B5E3D0"},
        "decision": {"fill": "#FFF8E7", "stroke": "#E9C77A"},
        "input_output": {"fill": "#EEFAF8", "stroke": "#9FD8CF"},
        "subprocess": {"fill": "#F0F8F4", "stroke": "#B8DDC8"},
    },
}

TASK_STAGE_DETAILS: dict[TaskStatus, tuple[int, str]] = {
    TaskStatus.WAITING: (5, "任务已创建，等待处理"),
    TaskStatus.SUBMITTING: (15, "正在提交生成请求"),
    TaskStatus.PROVIDER_QUEUED: (25, "模型服务正在排队"),
    TaskStatus.PROVIDER_PROCESSING: (55, "模型正在生成流程图"),
    TaskStatus.VALIDATING: (75, "正在校验流程图结构"),
    TaskStatus.RENDERING: (90, "正在生成 Mermaid 和导出结果"),
    TaskStatus.SUCCESS: (100, "流程图已生成"),
    TaskStatus.CANCELED: (0, "任务已取消"),
    TaskStatus.EXPIRED: (0, "任务已过期"),
}

_TIMEOUT_CODE = "PROVIDER_TASK_TIMEOUT"
_TIMEOUT_MESSAGE = "生成耗时较长，任务已超时，请重试或更换模型"
_FAILURE_STAGE = "流程图生成失败"
_CANCEL_PENDING = "cancel_pending"
_CANCELING = "canceling"
_PROVIDER_CANCELED = "canceled"

_SAFE_ERROR_MESSAGES = {
    "DIAGRAM_SCHEMA_INVALID": "生成结果不符合流程图规则，请重新描述流程后再试",
    "PROVIDER_AUTH_FAILED": "当前生成模型不可用，请稍后再试",
    "PROVIDER_NOT_CONFIGURED": "当前没有可用的生成模型，请稍后再试",
    "PROVIDER_RATE_LIMITED": "当前生成请求较多，任务正在重试",
    "PROVIDER_TASK_TIMEOUT": _TIMEOUT_MESSAGE,
    "PROVIDER_UNHEALTHY": "供应商服务暂时不可用，请稍后重试",
    "TASK_CANCELED": "任务已取消",
    "TASK_EXPIRED": "任务已过期，请重新生成",
}


@dataclass(frozen=True)
class TaskSnapshot:
    """脱离数据库会话后仍可安全用于供应商调用的任务快照。"""

    id: UUID
    user_id: str
    status: TaskStatus
    request_snapshot: dict[str, Any]
    provider_id: str | None
    model_name: str | None
    provider_request_id: str | None
    provider_status: str | None
    poll_count: int
    retry_count: int
    deadline_at: datetime | None
    created_at: datetime | None
    error_code: str | None


class TaskEngine:
    """执行创建后已冻结供应商选择的本地流程图任务。

    Worker 不调用 ``ProviderRouter.submit_with_fallback``：一旦任务已创建，
    只能使用该任务持久化的 ``provider_id``，避免真实调用失败时重复生成或
    隐式切换到 Mock/其他供应商。
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession] | None = None,
        registry: ProviderRegistry | None = None,
        schedule_execute: Callable[[UUID, int], None] | None = None,
        schedule_poll: Callable[[UUID, int], None] | None = None,
        schedule_cancel: Callable[[UUID, int], None] | None = None,
        schedule_export: Callable[[UUID], None] | None = None,
        now: Callable[[], datetime] | None = None,
        event_publisher: TaskEventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._registry = registry
        self._schedule_execute = schedule_execute or _default_schedule_execute
        self._schedule_poll = schedule_poll or _default_schedule_poll
        self._schedule_cancel = schedule_cancel or _default_schedule_cancel
        self._schedule_export = schedule_export or _default_schedule_export
        self._now = now or _utcnow
        self._event_publisher = event_publisher or publish_task_event

    async def execute(self, task_id: UUID) -> None:
        """提交尚未处理的任务，或重试一个已安排的提交。"""

        snapshot = await self._claim_submission(task_id)
        if snapshot is None:
            await self.resume(task_id)
            return

        try:
            registration = self._registration(snapshot)
            provider = self._provider(registration)
            submission = await _await_with_deadline(
                provider.submit(dict(snapshot.request_snapshot)),
                snapshot.deadline_at,
                self._now,
            )
        except ProviderTransportError as exc:
            await self._handle_submit_error(task_id, self._maybe_registration(snapshot), exc)
            return
        except ProviderSelectionError as exc:
            await self._fail_from_error(
                task_id,
                self._maybe_registration(snapshot),
                code=exc.code,
                operation="submit",
            )
            return
        except Exception:
            logger.exception("flowchart task provider submit failed taskId={}", task_id)
            await self._fail_from_error(
                task_id,
                self._maybe_registration(snapshot),
                code="PROVIDER_SUBMIT_FAILED",
                operation="submit",
            )
            return

        action, delay_seconds, result = await self._record_submission(
            task_id,
            registration,
            submission,
        )
        if action == "finalize" and result is not None:
            await self._validate_and_complete(task_id, result)
        elif action == "poll":
            self._schedule_poll(task_id, delay_seconds)
        elif action == "cancel":
            self._schedule_cancel(task_id, 0)

    async def poll(self, task_id: UUID) -> None:
        """轮询已提交的异步供应商任务。"""

        snapshot, should_cancel = await self._claim_poll(task_id)
        if should_cancel:
            self._schedule_cancel(task_id, 0)
        if snapshot is None:
            return

        try:
            registration = self._registration(snapshot)
            provider = self._provider(registration)
            result = await _await_with_deadline(
                provider.poll(
                    ProviderSubmission(
                        provider_request_id=snapshot.provider_request_id,
                        mode="async",
                        status=_provider_submission_status(snapshot.provider_status),
                    )
                ),
                snapshot.deadline_at,
                self._now,
            )
        except ProviderTransportError as exc:
            await self._handle_poll_error(task_id, self._maybe_registration(snapshot), exc)
            return
        except ProviderSelectionError as exc:
            await self._fail_from_error(
                task_id,
                self._maybe_registration(snapshot),
                code=exc.code,
                operation="poll",
            )
            return
        except Exception:
            logger.exception("flowchart task provider poll failed taskId={}", task_id)
            await self._fail_from_error(
                task_id,
                self._maybe_registration(snapshot),
                code="PROVIDER_SUBMIT_FAILED",
                operation="poll",
            )
            return

        action, delay_seconds, payload = await self._record_poll_result(
            task_id,
            registration,
            result,
        )
        if action == "finalize" and payload is not None:
            await self._validate_and_complete(task_id, payload)
        elif action == "poll":
            self._schedule_poll(task_id, delay_seconds)
        elif action == "cancel":
            self._schedule_cancel(task_id, 0)

    async def cancel_provider(self, task_id: UUID) -> None:
        """对已取消或超时任务发起尽力而为的供应商取消。"""

        snapshot = await self._claim_provider_cancel(task_id)
        if snapshot is None:
            return

        try:
            registration = self._registration(snapshot)
            provider = self._provider(registration)
            await provider.cancel(
                ProviderSubmission(
                    provider_request_id=snapshot.provider_request_id,
                    mode="async",
                    status=_provider_submission_status(snapshot.provider_status),
                )
            )
        except ProviderTransportError as exc:
            await self._record_cancel_result(
                task_id,
                self._maybe_registration(snapshot),
                succeeded=False,
                error=exc,
            )
            return
        except ProviderSelectionError as exc:
            await self._record_cancel_result(
                task_id,
                self._maybe_registration(snapshot),
                succeeded=False,
                error_code=exc.code,
            )
            return
        except Exception:
            logger.exception("flowchart task provider cancel failed taskId={}", task_id)
            await self._record_cancel_result(
                task_id,
                self._maybe_registration(snapshot),
                succeeded=False,
                error_code="PROVIDER_SUBMIT_FAILED",
            )
            return

        await self._record_cancel_result(task_id, registration, succeeded=True)

    async def resume(self, task_id: UUID) -> None:
        """恢复 Worker 在结构校验或渲染阶段中断的任务。"""

        payload: dict[str, Any] | None = None
        status: TaskStatus | None = None
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None:
                return
            if task.type != TaskType.DIAGRAM_GENERATE.value:
                return
            status = TaskStatus(task.status)
            if status not in {TaskStatus.VALIDATING, TaskStatus.RENDERING}:
                return
            if not isinstance(task.result, Mapping):
                self._mark_failed(task, code="DIAGRAM_SCHEMA_INVALID")
            else:
                payload = dict(task.result)
            if payload is None:
                await self._commit_task_update(session, task)
            else:
                await session.commit()

        if payload is None:
            return
        if status is TaskStatus.VALIDATING:
            await self._validate_and_complete(task_id, payload)
        else:
            await self._complete_document(task_id, payload)

    async def compensate(self, *, limit: int = COMPENSATION_LIMIT) -> int:
        """恢复遗漏消息、收敛僵尸任务，并处理未完成的供应商取消请求。"""

        now = self._now()
        execute_ids: list[UUID] = []
        poll_ids: list[UUID] = []
        cancel_ids: list[UUID] = []
        export_ids: list[UUID] = []
        handled_ids: set[UUID] = set()
        changed_tasks: list[FlowchartTask] = []
        active_statuses = [
            TaskStatus.WAITING.value,
            TaskStatus.SUBMITTING.value,
            TaskStatus.PROVIDER_QUEUED.value,
            TaskStatus.PROVIDER_PROCESSING.value,
            TaskStatus.VALIDATING.value,
            TaskStatus.RENDERING.value,
        ]
        cancellation_statuses = [
            TaskStatus.CANCELED.value,
            TaskStatus.EXPIRED.value,
            TaskStatus.FAILED.value,
        ]

        async with self._session_factory() as session:
            result = await session.execute(
                select(FlowchartTask)
                .where(
                    or_(
                        FlowchartTask.status.in_(active_statuses),
                        and_(
                            FlowchartTask.status.in_(cancellation_statuses),
                            FlowchartTask.provider_request_id.is_not(None),
                            or_(
                                FlowchartTask.provider_status.is_(None),
                                FlowchartTask.provider_status != _PROVIDER_CANCELED,
                            ),
                        ),
                    )
                )
                .order_by(FlowchartTask.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            tasks = list(result.scalars().all())
            for task in tasks:
                status = TaskStatus(task.status)
                task_id = _to_uuid(task.id)

                # SVG/PNG 导出任务由 Chromium Worker 执行；不要把它们送入
                # 供应商生成状态机，也不要按供应商超时规则标记失败。
                if task.type == TaskType.DIAGRAM_EXPORT.value:
                    if is_export_render_claimable(task, now=now):
                        export_ids.append(task_id)
                    continue

                if _is_stale_unsubmitted_generation_task(task, status=status, now=now):
                    self._mark_expired(task)
                    changed_tasks.append(task)
                    handled_ids.add(task_id)
                    if task.provider_request_id:
                        cancel_ids.append(task_id)
                    continue

                if status not in TERMINAL_TASK_STATUSES and _is_due(task.deadline_at, now):
                    self._mark_failed(task, code=_TIMEOUT_CODE)
                    changed_tasks.append(task)
                    handled_ids.add(task_id)
                    if task.provider_request_id:
                        cancel_ids.append(task_id)
                    continue

                if status is TaskStatus.WAITING:
                    execute_ids.append(task_id)
                elif status is TaskStatus.SUBMITTING and _is_due(task.next_poll_at, now):
                    execute_ids.append(task_id)
                elif status in {TaskStatus.PROVIDER_QUEUED, TaskStatus.PROVIDER_PROCESSING} and _is_due(
                    task.next_poll_at, now
                ):
                    poll_ids.append(task_id)
                elif status in {TaskStatus.VALIDATING, TaskStatus.RENDERING}:
                    execute_ids.append(task_id)
                elif (
                    status in {TaskStatus.CANCELED, TaskStatus.EXPIRED}
                    or (status is TaskStatus.FAILED and task.error_code == _TIMEOUT_CODE)
                ) and task.provider_request_id:
                    cancel_ids.append(task_id)
            await session.commit()
            for changed_task in changed_tasks:
                await self._publish_task_event(changed_task)

        for task_id in execute_ids:
            self._schedule_execute(task_id, 0)
        for task_id in poll_ids:
            self._schedule_poll(task_id, 0)
        for task_id in cancel_ids:
            self._schedule_cancel(task_id, 0)
        for task_id in export_ids:
            self._schedule_export(task_id)
        handled_ids.update(execute_ids)
        handled_ids.update(poll_ids)
        handled_ids.update(cancel_ids)
        handled_ids.update(export_ids)
        return len(handled_ids)

    async def _claim_submission(self, task_id: UUID) -> TaskSnapshot | None:
        timeout_snapshot: TaskSnapshot | None = None
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None:
                return None
            if task.type != TaskType.DIAGRAM_GENERATE.value:
                return None
            status = TaskStatus(task.status)
            can_retry_submit = status is TaskStatus.SUBMITTING and _is_due(task.next_poll_at, self._now())
            if status is not TaskStatus.WAITING and not can_retry_submit:
                return None

            now = self._now()
            if _is_due(task.deadline_at, now):
                self._mark_failed(task, code=_TIMEOUT_CODE)
                timeout_snapshot = _snapshot(task)
            else:
                _set_stage(task, TaskStatus.SUBMITTING)
                task.next_poll_at = now + timedelta(seconds=SUBMIT_WATCHDOG_SECONDS)
                if task.queue_wait_ms is None:
                    task.queue_wait_ms = _elapsed_ms(task.created_at, now)
            await self._commit_task_update(session, task)

            if timeout_snapshot is None:
                return _snapshot(task)

        if timeout_snapshot.provider_request_id:
            self._schedule_cancel(task_id, 0)
        return None

    async def _record_submission(
        self,
        task_id: UUID,
        registration: ProviderRegistration,
        submission: ProviderSubmission,
    ) -> tuple[str, int, dict[str, Any] | None]:
        cancel_after_commit = False
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None:
                return "skip", 0, None
            status = TaskStatus(task.status)
            if status is TaskStatus.CANCELED:
                task.provider_request_id = submission.provider_request_id or task.provider_request_id
                task.provider_status = _CANCEL_PENDING if task.provider_request_id else submission.status
                _append_provider_call(session, task, registration, operation="submit", status="canceled")
                await session.commit()
                return "cancel" if task.provider_request_id else "skip", 0, None
            if status is not TaskStatus.SUBMITTING:
                return "skip", 0, None

            now = self._now()
            task.provider_request_id = submission.provider_request_id or task.provider_request_id
            task.provider_status = submission.status
            _append_provider_call(
                session,
                task,
                registration,
                operation="submit",
                status="failed" if submission.status == "failed" else "succeeded",
            )
            if _is_due(task.deadline_at, now):
                self._mark_failed(task, code=_TIMEOUT_CODE)
                cancel_after_commit = bool(task.provider_request_id)
                action: tuple[str, int, dict[str, Any] | None] = ("cancel", 0, None)
            elif submission.status == "succeeded":
                if submission.result is None:
                    self._mark_failed(task, code="DIAGRAM_SCHEMA_INVALID")
                    action = ("skip", 0, None)
                else:
                    _set_stage(task, TaskStatus.VALIDATING)
                    task.result = dict(submission.result)
                    task.next_poll_at = None
                    action = ("finalize", 0, dict(submission.result))
            elif submission.status in {"queued", "processing"}:
                provider_status = (
                    TaskStatus.PROVIDER_QUEUED
                    if submission.status == "queued"
                    else TaskStatus.PROVIDER_PROCESSING
                )
                _set_stage(task, provider_status)
                delay_seconds = _poll_delay(submission.retry_after_seconds, task.poll_count)
                task.next_poll_at = now + timedelta(seconds=delay_seconds)
                action = ("poll", delay_seconds, None)
            else:
                self._mark_failed(task, code="PROVIDER_SUBMIT_FAILED")
                action = ("skip", 0, None)
            await self._commit_task_update(session, task)

        if cancel_after_commit:
            return "cancel", 0, None
        return action

    async def _handle_submit_error(
        self,
        task_id: UUID,
        registration: ProviderRegistration | None,
        error: ProviderTransportError,
    ) -> None:
        action = "skip"
        delay_seconds = 0
        cancel_after_commit = False
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None:
                return
            status = TaskStatus(task.status)
            if status is TaskStatus.CANCELED:
                if registration is not None:
                    _append_provider_call(
                        session,
                        task,
                        registration,
                        operation="submit",
                        status="canceled",
                        error=error,
                    )
                await session.commit()
                if task.provider_request_id:
                    self._schedule_cancel(task_id, 0)
                return
            if status is not TaskStatus.SUBMITTING:
                return

            now = self._now()
            if registration is not None:
                _append_provider_call(session, task, registration, operation="submit", status="failed", error=error)
            if _is_due(task.deadline_at, now):
                self._mark_failed(task, code=_TIMEOUT_CODE)
                cancel_after_commit = bool(task.provider_request_id)
            elif error.retryable:
                task.retry_count += 1
                task.last_provider_error = error.code
                task.error_code = None
                task.error_message = None
                delay_seconds = _poll_delay(error.retry_after_seconds, max(task.retry_count - 1, 0))
                task.next_poll_at = now + timedelta(seconds=delay_seconds)
                task.stage = "供应商暂时不可用，正在重试提交"
                action = "execute"
            else:
                self._mark_failed(task, code=error.code)
            await self._commit_task_update(session, task)

        if cancel_after_commit:
            self._schedule_cancel(task_id, 0)
        elif action == "execute":
            self._schedule_execute(task_id, delay_seconds)

    async def _claim_poll(self, task_id: UUID) -> tuple[TaskSnapshot | None, bool]:
        should_cancel = False
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None:
                return None, False
            if task.type != TaskType.DIAGRAM_GENERATE.value:
                return None, False
            status = TaskStatus(task.status)
            if status is TaskStatus.CANCELED:
                return None, bool(task.provider_request_id)
            if status not in {TaskStatus.PROVIDER_QUEUED, TaskStatus.PROVIDER_PROCESSING}:
                return None, False

            now = self._now()
            if _is_due(task.deadline_at, now):
                self._mark_failed(task, code=_TIMEOUT_CODE)
                should_cancel = bool(task.provider_request_id)
                await self._commit_task_update(session, task)
                return None, should_cancel
            if task.next_poll_at is None or task.next_poll_at > now:
                return None, False

            # Worker 崩溃时由 Beat 在 watchdog 到期后重新调度一次轮询。
            task.next_poll_at = now + timedelta(seconds=MAX_POLL_SECONDS)
            task.poll_count += 1
            await session.commit()
            return _snapshot(task), False

    async def _record_poll_result(
        self,
        task_id: UUID,
        registration: ProviderRegistration,
        result: ProviderPollResult,
    ) -> tuple[str, int, dict[str, Any] | None]:
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None:
                return "skip", 0, None
            status = TaskStatus(task.status)
            if status is TaskStatus.CANCELED:
                _append_provider_call(session, task, registration, operation="poll", status="canceled")
                await session.commit()
                return "cancel" if task.provider_request_id else "skip", 0, None
            if status not in {TaskStatus.PROVIDER_QUEUED, TaskStatus.PROVIDER_PROCESSING}:
                return "skip", 0, None

            now = self._now()
            task.provider_status = result.status
            _append_provider_call(
                session,
                task,
                registration,
                operation="poll",
                status={"failed": "failed", "canceled": "canceled"}.get(result.status, "succeeded"),
                error_code=result.error_code,
            )
            if _is_due(task.deadline_at, now):
                self._mark_failed(task, code=_TIMEOUT_CODE)
                await self._commit_task_update(session, task)
                return "cancel" if task.provider_request_id else "skip", 0, None
            if result.status == "succeeded":
                if result.result is None:
                    self._mark_failed(task, code="DIAGRAM_SCHEMA_INVALID")
                    action: tuple[str, int, dict[str, Any] | None] = ("skip", 0, None)
                else:
                    _set_stage(task, TaskStatus.VALIDATING)
                    task.result = dict(result.result)
                    task.next_poll_at = None
                    action = ("finalize", 0, dict(result.result))
            elif result.status == "canceled":
                _set_stage(task, TaskStatus.CANCELED)
                task.next_poll_at = None
                task.error_code = "TASK_CANCELED"
                task.error_message = _safe_message("TASK_CANCELED")
                action = ("skip", 0, None)
            elif result.status == "failed":
                self._mark_failed(task, code=result.error_code or "PROVIDER_SUBMIT_FAILED")
                action = ("skip", 0, None)
            else:
                next_status = (
                    TaskStatus.PROVIDER_QUEUED
                    if result.status == "queued"
                    else TaskStatus.PROVIDER_PROCESSING
                )
                _set_stage(task, next_status, progress=_provider_progress(next_status, result.progress, task.progress))
                delay_seconds = _poll_delay(result.retry_after_seconds, task.poll_count)
                task.next_poll_at = now + timedelta(seconds=delay_seconds)
                task.error_code = None
                task.error_message = None
                action = ("poll", delay_seconds, None)
            await self._commit_task_update(session, task)
            return action

    async def _handle_poll_error(
        self,
        task_id: UUID,
        registration: ProviderRegistration | None,
        error: ProviderTransportError,
    ) -> None:
        action = "skip"
        delay_seconds = 0
        cancel_after_commit = False
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None:
                return
            status = TaskStatus(task.status)
            if status is TaskStatus.CANCELED:
                if registration is not None:
                    _append_provider_call(
                        session,
                        task,
                        registration,
                        operation="poll",
                        status="canceled",
                        error=error,
                    )
                await session.commit()
                if task.provider_request_id:
                    self._schedule_cancel(task_id, 0)
                return
            if status not in {TaskStatus.PROVIDER_QUEUED, TaskStatus.PROVIDER_PROCESSING}:
                return

            now = self._now()
            if registration is not None:
                _append_provider_call(session, task, registration, operation="poll", status="failed", error=error)
            if _is_due(task.deadline_at, now):
                self._mark_failed(task, code=_TIMEOUT_CODE)
                cancel_after_commit = bool(task.provider_request_id)
            elif error.retryable:
                task.retry_count += 1
                task.last_provider_error = error.code
                task.error_code = None
                task.error_message = None
                delay_seconds = _poll_delay(error.retry_after_seconds, max(task.retry_count - 1, 0))
                task.next_poll_at = now + timedelta(seconds=delay_seconds)
                task.stage = "供应商暂时不可用，正在重试查询"
                action = "poll"
            else:
                self._mark_failed(task, code=error.code)
            await self._commit_task_update(session, task)

        if cancel_after_commit:
            self._schedule_cancel(task_id, 0)
        elif action == "poll":
            self._schedule_poll(task_id, delay_seconds)

    async def _validate_and_complete(self, task_id: UUID, payload: Mapping[str, Any]) -> None:
        if not await self._can_validate(task_id):
            return
        try:
            document = compile_generated_diagram_document(dict(payload))
        except (TypeError, ValidationError, ValueError):
            await self._fail_from_error(
                task_id,
                registration=None,
                code="DIAGRAM_SCHEMA_INVALID",
                operation="validate",
            )
            return

        await self._complete_document(task_id, document.model_dump(mode="json", by_alias=True))

    async def _can_validate(self, task_id: UUID) -> bool:
        cancel_after_commit = False
        valid = False
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None or TaskStatus(task.status) is not TaskStatus.VALIDATING:
                return False
            if _is_due(task.deadline_at, self._now()):
                self._mark_failed(task, code=_TIMEOUT_CODE)
                cancel_after_commit = bool(task.provider_request_id)
                await self._commit_task_update(session, task)
            else:
                valid = True
        if cancel_after_commit:
            self._schedule_cancel(task_id, 0)
        return valid

    async def _complete_document(self, task_id: UUID, payload: dict[str, Any]) -> None:
        cancel_after_commit = False
        timed_out = False
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None or TaskStatus(task.status) not in {
                TaskStatus.VALIDATING,
                TaskStatus.RENDERING,
            }:
                return
            if TaskStatus(task.status) is TaskStatus.VALIDATING:
                if _is_due(task.deadline_at, self._now()):
                    self._mark_failed(task, code=_TIMEOUT_CODE)
                    cancel_after_commit = bool(task.provider_request_id)
                    timed_out = True
                else:
                    _set_stage(task, TaskStatus.RENDERING)
                    task.result = payload
                await self._commit_task_update(session, task)

        if cancel_after_commit:
            self._schedule_cancel(task_id, 0)
            return

        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None or TaskStatus(task.status) is not TaskStatus.RENDERING:
                return
            if _is_due(task.deadline_at, self._now()):
                self._mark_failed(task, code=_TIMEOUT_CODE)
                cancel_after_commit = bool(task.provider_request_id)
            else:
                payload = _apply_task_theme(payload, task)
                payload = _attach_task_metadata(payload, task)
                document = create_generated_document(task, payload, now=self._now())
                session.add(document)
                task.document_id = _to_uuid(document.id)
                _set_stage(task, TaskStatus.SUCCESS)
                task.result = payload
                task.next_poll_at = None
                task.provider_status = "succeeded"
                task.error_code = None
                task.error_message = None
                task.provider_wait_ms = _elapsed_ms(task.created_at, self._now())
            await self._commit_task_update(session, task)

        if cancel_after_commit:
            self._schedule_cancel(task_id, 0)

    async def _fail_from_error(
        self,
        task_id: UUID,
        registration: ProviderRegistration | None,
        *,
        code: str,
        operation: str,
    ) -> None:
        cancel_after_commit = False
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None or TaskStatus(task.status) in TERMINAL_TASK_STATUSES:
                return
            if registration is not None:
                _append_provider_call(
                    session,
                    task,
                    registration,
                    operation=operation,
                    status="failed",
                    error_code=code,
                )
            self._mark_failed(task, code=code)
            cancel_after_commit = bool(task.provider_request_id and code == _TIMEOUT_CODE)
            await self._commit_task_update(session, task)
        if cancel_after_commit:
            self._schedule_cancel(task_id, 0)

    async def _claim_provider_cancel(self, task_id: UUID) -> TaskSnapshot | None:
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None or not task.provider_request_id:
                return None
            status = TaskStatus(task.status)
            is_timeout = status is TaskStatus.FAILED and task.error_code == _TIMEOUT_CODE
            if status not in {TaskStatus.CANCELED, TaskStatus.EXPIRED} and not is_timeout:
                return None
            if task.provider_status == _PROVIDER_CANCELED:
                return None
            task.provider_status = _CANCELING
            await session.commit()
            return _snapshot(task)

    async def _record_cancel_result(
        self,
        task_id: UUID,
        registration: ProviderRegistration | None,
        *,
        succeeded: bool,
        error: ProviderTransportError | None = None,
        error_code: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            task = await _get_locked_task(session, task_id)
            if task is None:
                return
            if registration is not None:
                _append_provider_call(
                    session,
                    task,
                    registration,
                    operation="cancel",
                    status="succeeded" if succeeded else "failed",
                    error=error,
                    error_code=error_code,
                )
            task.provider_status = _PROVIDER_CANCELED if succeeded else _CANCEL_PENDING
            await session.commit()

    def _registration(self, snapshot: TaskSnapshot) -> ProviderRegistration:
        if not snapshot.provider_id:
            raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "当前没有可用的生成模型")
        return self._registry_or_default().get_registration(snapshot.provider_id)

    def _maybe_registration(self, snapshot: TaskSnapshot) -> ProviderRegistration | None:
        try:
            return self._registration(snapshot)
        except ProviderSelectionError:
            return None

    def _provider(self, registration: ProviderRegistration):
        return self._registry_or_default().build_provider(registration.provider_id)

    def _registry_or_default(self) -> ProviderRegistry:
        return self._registry or get_provider_registry()

    async def _publish_task_event(self, task: FlowchartTask) -> None:
        event = task_status_event_from_task(task)
        try:
            await self._event_publisher(event)
        except Exception:
            logger.warning("flowchart task event publish deferred taskId={}", task.id)

    async def _commit_task_update(self, session: AsyncSession, task: FlowchartTask) -> None:
        """提交任务状态后发布通知；通知异常不能回滚业务事实。"""

        await session.commit()
        await self._publish_task_event(task)

    def _mark_failed(self, task: FlowchartTask, *, code: str) -> None:
        task.status = TaskStatus.FAILED.value
        task.stage = _TIMEOUT_MESSAGE if code == _TIMEOUT_CODE else _FAILURE_STAGE
        task.next_poll_at = None
        task.error_code = code
        task.error_message = _safe_message(code)

    def _mark_expired(self, task: FlowchartTask) -> None:
        """将未提交给供应商的过期生成任务收敛为可重试终态。"""

        # _set_stage 使用现有进度与状态默认进度的较大值，避免终态事件让
        # 已展示的任务进度倒退。
        _set_stage(task, TaskStatus.EXPIRED)
        task.next_poll_at = None
        task.error_code = "TASK_EXPIRED"
        task.error_message = _safe_message(task.error_code)


async def _get_locked_task(session: AsyncSession, task_id: UUID) -> FlowchartTask | None:
    result = await session.execute(
        select(FlowchartTask).where(FlowchartTask.id == task_id).with_for_update()
    )
    return result.scalar_one_or_none()


def _set_stage(
    task: FlowchartTask,
    status: TaskStatus,
    *,
    progress: int | None = None,
) -> None:
    default_progress, stage = TASK_STAGE_DETAILS[status]
    if status is TaskStatus.SUCCESS:
        task.progress = 100
    else:
        target = default_progress if progress is None else progress
        task.progress = max(int(task.progress or 0), target)
    task.status = status.value
    task.stage = stage


def _append_provider_call(
    session: AsyncSession,
    task: FlowchartTask,
    registration: ProviderRegistration,
    *,
    operation: str,
    status: str,
    error: ProviderTransportError | None = None,
    error_code: str | None = None,
) -> None:
    config = registration.config
    code = error.code if error is not None else error_code
    session.add(
        FlowchartProviderCall(
            id=uuid_utils.uuid7(),
            task_id=_to_uuid(task.id),
            user_id=task.user_id,
            provider_id=registration.provider_id,
            model_name=config.model,
            protocol=_enum_value(config.protocol),
            request_id=task.provider_request_id or (error.request_id if error is not None else None),
            operation=operation,
            status=status,
            poll_count=task.poll_count,
            retry_count=task.retry_count,
            error_code=code,
            error_message=_safe_message(code) if code else None,
        )
    )


def _snapshot(task: FlowchartTask) -> TaskSnapshot:
    return TaskSnapshot(
        id=_to_uuid(task.id),
        user_id=task.user_id,
        status=TaskStatus(task.status),
        request_snapshot=dict(task.request_snapshot),
        provider_id=task.provider_id,
        model_name=task.model_name,
        provider_request_id=task.provider_request_id,
        provider_status=task.provider_status,
        poll_count=task.poll_count,
        retry_count=task.retry_count,
        deadline_at=task.deadline_at,
        created_at=task.created_at,
        error_code=task.error_code,
    )


def _attach_task_metadata(payload: dict[str, Any], task: FlowchartTask) -> dict[str, Any]:
    result = dict(payload)
    metadata = dict(result.get("metadata") or {})
    metadata.update(
        {
            "generatedBy": task.provider_id,
            "model": task.model_name,
            "sourceTaskId": str(task.id),
        }
    )
    result["metadata"] = metadata
    return result


def _apply_task_theme(payload: dict[str, Any], task: FlowchartTask) -> dict[str, Any]:
    """以任务选项覆盖模型样式，保证生成结果使用用户选择的主题。"""

    snapshot = task.request_snapshot if isinstance(task.request_snapshot, Mapping) else {}
    theme = str(
        snapshot.get("diagram_theme")
        or snapshot.get("diagramTheme")
        or snapshot.get("theme")
        or "blue"
    ).lower()
    palette = _DIAGRAM_THEME_STYLES.get(theme, _DIAGRAM_THEME_STYLES["blue"])
    result = dict(payload)
    nodes = result.get("nodes")
    if isinstance(nodes, list):
        themed_nodes: list[Any] = []
        for node in nodes:
            if not isinstance(node, Mapping):
                themed_nodes.append(node)
                continue
            themed_node = dict(node)
            node_style = palette.get(str(themed_node.get("type")))
            if node_style is not None:
                themed_node["style"] = dict(node_style)
            themed_nodes.append(themed_node)
        result["nodes"] = themed_nodes

    metadata = dict(result.get("metadata") or {})
    metadata["theme"] = theme if theme in _DIAGRAM_THEME_STYLES else "blue"
    result["metadata"] = metadata
    return result


def _provider_progress(status: TaskStatus, progress: int | None, current_progress: int) -> int:
    if progress is None:
        return TASK_STAGE_DETAILS[status][0]
    lower, upper = (25, 54) if status is TaskStatus.PROVIDER_QUEUED else (55, 74)
    return max(current_progress, min(upper, max(lower, progress)))


def _provider_submission_status(status: str | None) -> str:
    return status if status in {"queued", "processing", "succeeded", "failed"} else "processing"


async def _await_with_deadline(awaitable, deadline: datetime | None, now: Callable[[], datetime]):
    if deadline is None:
        return await awaitable
    remaining = _remaining_seconds(deadline, now())
    if remaining <= 0:
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
        raise ProviderTransportError(
            _TIMEOUT_MESSAGE,
            code=_TIMEOUT_CODE,
            retryable=False,
            fallback_allowed=False,
        )
    try:
        return await asyncio.wait_for(awaitable, timeout=remaining)
    except asyncio.TimeoutError:
        raise ProviderTransportError(
            _TIMEOUT_MESSAGE,
            code=_TIMEOUT_CODE,
            retryable=False,
            fallback_allowed=False,
        ) from None


def _poll_delay(retry_after_seconds: int | None, count: int) -> int:
    if retry_after_seconds is not None:
        return max(MIN_POLL_SECONDS, min(MAX_POLL_SECONDS, retry_after_seconds))
    index = min(max(count, 0), len(POLL_BACKOFF_SECONDS) - 1)
    return POLL_BACKOFF_SECONDS[index]


def _safe_message(code: str | None) -> str:
    return _SAFE_ERROR_MESSAGES.get(code or "", "流程图生成失败，请稍后重试")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _is_due(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value <= now


def _is_stale_unsubmitted_generation_task(
    task: FlowchartTask,
    *,
    status: TaskStatus,
    now: datetime,
) -> bool:
    """只处理生成任务，避免影响独立 Chromium 导出任务的恢复策略。"""

    if task.type != TaskType.DIAGRAM_GENERATE.value:
        return False
    if status not in {TaskStatus.WAITING, TaskStatus.SUBMITTING}:
        return False
    created_at = task.created_at
    if created_at is None:
        return False
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(UTC).replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.astimezone(UTC).replace(tzinfo=None)
    return now - created_at > ZOMBIE_SUBMISSION_TIMEOUT


def _remaining_seconds(deadline: datetime, now: datetime) -> float:
    if deadline.tzinfo is not None:
        deadline = deadline.astimezone(UTC).replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.astimezone(UTC).replace(tzinfo=None)
    return (deadline - now).total_seconds()


def _elapsed_ms(start: datetime | None, end: datetime) -> int | None:
    if start is None:
        return None
    if start.tzinfo is not None:
        start = start.astimezone(UTC).replace(tzinfo=None)
    return max(0, int((end - start).total_seconds() * 1000))


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _to_uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _default_schedule_execute(task_id: UUID, countdown: int) -> None:
    from app.workers.tasks import enqueue_task_execution

    enqueue_task_execution(task_id, countdown=countdown)


def _default_schedule_poll(task_id: UUID, countdown: int) -> None:
    from app.workers.tasks import enqueue_task_poll

    enqueue_task_poll(task_id, countdown=countdown)


def _default_schedule_cancel(task_id: UUID, countdown: int) -> None:
    from app.workers.tasks import enqueue_task_cancel

    enqueue_task_cancel(task_id, countdown=countdown)


def _default_schedule_export(task_id: UUID) -> None:
    from app.workers.tasks import enqueue_document_export

    enqueue_document_export(task_id)


__all__ = [
    "COMPENSATION_LIMIT",
    "MAX_POLL_SECONDS",
    "MIN_POLL_SECONDS",
    "POLL_BACKOFF_SECONDS",
    "SUBMIT_WATCHDOG_SECONDS",
    "TASK_STAGE_DETAILS",
    "TaskEngine",
    "TaskSnapshot",
]
