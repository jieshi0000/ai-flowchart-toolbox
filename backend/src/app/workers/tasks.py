"""Celery 任务入口。

任务函数保持同步，以适配 Celery Worker；实际业务编排委托给
``TaskEngine`` 的异步实现，便于单元测试和 FastAPI 以外的调用方复用。
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from celery.signals import worker_shutdown
from loguru import logger

from app.services.document_service import compile_document_mermaid
from app.services.export_service import cleanup_expired_export_files, render_document_export
from app.services.task_engine import TaskEngine
from app.workers.celery_app import celery_app


_runner: asyncio.Runner | None = None


@celery_app.task(name="flowchart.tasks.execute", ignore_result=True)
def execute_flowchart_task(task_id: str) -> None:
    _run(TaskEngine().execute(_parse_task_id(task_id)))


@celery_app.task(name="flowchart.tasks.poll", ignore_result=True)
def poll_flowchart_task(task_id: str) -> None:
    _run(TaskEngine().poll(_parse_task_id(task_id)))


@celery_app.task(name="flowchart.tasks.cancel", ignore_result=True)
def cancel_flowchart_task(task_id: str) -> None:
    _run(TaskEngine().cancel_provider(_parse_task_id(task_id)))


@celery_app.task(name="flowchart.tasks.compensate", ignore_result=True)
def compensate_flowchart_tasks() -> None:
    _run(TaskEngine().compensate())


@celery_app.task(name="flowchart.documents.compile_mermaid", ignore_result=True)
def compile_flowchart_document_mermaid(document_id: str, version: int) -> None:
    _run(compile_document_mermaid(_parse_task_id(document_id), int(version)))


@celery_app.task(name="flowchart.documents.export", ignore_result=True)
def export_flowchart_document(task_id: str) -> None:
    _run(render_document_export(_parse_task_id(task_id)))


@celery_app.task(name="flowchart.files.cleanup", ignore_result=True)
def cleanup_flowchart_export_files() -> None:
    _run(cleanup_expired_export_files())


def enqueue_task_execution(task_id: UUID, *, countdown: int = 0) -> None:
    _enqueue(execute_flowchart_task, task_id, countdown)


def enqueue_task_poll(task_id: UUID, *, countdown: int = 0) -> None:
    _enqueue(poll_flowchart_task, task_id, countdown)


def enqueue_task_cancel(task_id: UUID, *, countdown: int = 0) -> None:
    _enqueue(cancel_flowchart_task, task_id, countdown)


def enqueue_document_mermaid_compilation(document_id: UUID, version: int) -> None:
    try:
        compile_flowchart_document_mermaid.apply_async(args=[str(document_id), int(version)])
    except Exception:
        logger.warning("flowchart Mermaid compile enqueue deferred documentId={}", document_id)


def enqueue_document_export(task_id: UUID) -> None:
    try:
        export_flowchart_document.apply_async(args=[str(task_id)])
    except Exception:
        logger.warning("flowchart export enqueue deferred taskId={}", task_id)


def _enqueue(task, task_id: UUID, countdown: int) -> None:
    try:
        task.apply_async(args=[str(task_id)], countdown=max(0, int(countdown)))
    except Exception:
        # 任务已经提交到 PostgreSQL；Beat 会在 Redis 恢复后补偿遗漏消息。
        # 不记录异常对象，避免连接字符串等运行时配置进入普通日志。
        logger.warning("flowchart task enqueue deferred taskId={}", task_id)


def _run(coroutine) -> None:
    """在同一 Celery Worker 进程内复用事件循环和 asyncpg 连接池。"""

    global _runner
    if _runner is None:
        _runner = asyncio.Runner()
    _runner.run(coroutine)


def _close_runner(**_: object) -> None:
    """在 Worker 退出前释放 asyncpg 连接与事件循环。"""

    global _runner
    if _runner is not None:
        _runner.close()
        _runner = None


worker_shutdown.connect(_close_runner, weak=False)


def _parse_task_id(value: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError):
        logger.warning("ignore flowchart task with invalid taskId")
        raise


__all__ = [
    "cancel_flowchart_task",
    "cleanup_flowchart_export_files",
    "compile_flowchart_document_mermaid",
    "compensate_flowchart_tasks",
    "enqueue_document_mermaid_compilation",
    "enqueue_document_export",
    "enqueue_task_cancel",
    "enqueue_task_execution",
    "enqueue_task_poll",
    "execute_flowchart_task",
    "export_flowchart_document",
    "poll_flowchart_task",
]
