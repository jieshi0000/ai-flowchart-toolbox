from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.task import FlowchartTask
from app.providers.base import ModelProvider, ProviderPollResult, ProviderSubmission
from app.providers.provider_registry import ProviderRegistry
from app.providers.transport import ProviderHTTPError, ProviderResponseError
from app.schemas.provider import ProviderConfig, ProviderHealth
from app.schemas.task import TaskStatus, TaskType
from app.services.diagram_service import compile_diagram_document
from app.services.task_engine import TaskEngine
from tests.unit.provider_fixtures import provider_entry


@pytest.fixture(autouse=True)
def disable_default_task_event_publisher(monkeypatch):
    async def publish_nothing(_event):
        return None

    monkeypatch.setattr("app.services.task_engine.publish_task_event", publish_nothing)


class _ScalarResult:
    def __init__(self, task):
        self.task = task

    def scalar_one_or_none(self):
        return self.task

    def scalars(self):
        return SimpleNamespace(all=lambda: [self.task] if self.task is not None else [])


class _Session:
    def __init__(self, task):
        self.task = task
        self.added = []
        self.commit_count = 0

    async def execute(self, statement):
        return _ScalarResult(self.task)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commit_count += 1


def _session_factory(session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


class _Provider(ModelProvider):
    def __init__(self, *, submission=None, poll_results=None, error=None):
        self.submission = submission
        self.poll_results = list(poll_results or [])
        self.error = error
        self.submit_calls = 0
        self.poll_calls = 0
        self.cancel_calls = 0

    async def submit(self, request):
        self.submit_calls += 1
        if self.error is not None:
            raise self.error
        return self.submission

    async def poll(self, submission):
        self.poll_calls += 1
        return self.poll_results.pop(0)

    async def cancel(self, submission):
        self.cancel_calls += 1

    async def health_check(self):
        return ProviderHealth(status="healthy")


def _registry(provider):
    config = ProviderConfig.model_validate(
        provider_entry(
            "provider-a",
            key_env="PROVIDER_A_KEY",
            priority=100,
            model="model-a",
            displayName="model-a",
        )
    )
    return ProviderRegistry(
        [config],
        providers={"provider-a": provider},
        key_lookup={"PROVIDER_A_KEY": "test-key"}.get,
    )


def _diagram():
    return {
        "title": "审批流程",
        "direction": "TB",
        "nodes": [
            {"id": "start", "type": "start", "label": "开始"},
            {"id": "end", "type": "end", "label": "结束"},
        ],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }


def _task(
    *,
    status="waiting",
    deadline=None,
    provider_request_id=None,
    task_type=TaskType.DIAGRAM_GENERATE.value,
):
    now = datetime(2026, 8, 17, 12, 0, 0)
    return FlowchartTask(
        id=uuid4(),
        user_id="user-a",
        type=task_type,
        status=status,
        progress=5,
        stage="任务已创建，等待处理",
        request_snapshot={
            "type": "diagram_generate",
            "prompt": "审批流程",
            "direction": "TB",
            "detailLevel": "standard",
        },
        provider_id="provider-a",
        model_name="model-a",
        provider_request_id=provider_request_id,
        provider_status="processing" if provider_request_id else None,
        idempotency_key=str(uuid4()),
        poll_count=0,
        retry_count=0,
        next_poll_at=None,
        deadline_at=deadline or now + timedelta(minutes=10),
        expires_at=now + timedelta(days=7),
        created_at=now - timedelta(seconds=2),
    )


@pytest.mark.asyncio
async def test_execute_sync_provider_reaches_success_and_compiles_mermaid():
    provider = _Provider(
        submission=ProviderSubmission(
            provider_request_id="request-1",
            mode="sync",
            status="succeeded",
            result=_diagram(),
        )
    )
    task = _task()
    session = _Session(task)
    schedule_poll = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=_registry(provider),
        schedule_poll=schedule_poll,
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    await engine.execute(task.id)

    assert provider.submit_calls == 1
    assert task.status == TaskStatus.SUCCESS.value
    assert task.progress == 100
    assert task.result["mermaidSource"].startswith("flowchart TB")
    assert task.result["metadata"]["sourceTaskId"] == str(task.id)
    schedule_poll.assert_not_called()
    assert [
        call.operation for call in session.added if hasattr(call, "operation")
    ] == ["submit"]
    document = next(call for call in session.added if not hasattr(call, "operation"))
    assert str(task.document_id) == str(document.id)
    assert document.version == 1
    assert document.mermaid_source.startswith("flowchart TB")


@pytest.mark.asyncio
async def test_execute_preserves_a_safe_model_mermaid_preview():
    model_source = 'flowchart LR\nn0(["开始"])\nn1(["结束"])\nn0 --> n1'
    result = _diagram()
    result.update(direction="LR", mermaidSource=model_source)
    provider = _Provider(
        submission=ProviderSubmission(
            provider_request_id="request-1",
            mode="sync",
            status="succeeded",
            result=result,
        )
    )
    task = _task()
    session = _Session(task)
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=_registry(provider),
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    await engine.execute(task.id)

    assert task.status == TaskStatus.SUCCESS.value
    assert task.result["mermaidSource"] == model_source
    document = next(call for call in session.added if not hasattr(call, "operation"))
    assert document.mermaid_source == model_source


@pytest.mark.asyncio
async def test_execute_publishes_events_for_each_visible_status_transition():
    provider = _Provider(
        submission=ProviderSubmission(
            provider_request_id="request-1",
            mode="sync",
            status="succeeded",
            result=_diagram(),
        )
    )
    task = _task()
    session = _Session(task)
    publisher = AsyncMock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=_registry(provider),
        event_publisher=publisher,
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    await engine.execute(task.id)

    assert [call.args[0].status for call in publisher.await_args_list] == [
        TaskStatus.SUBMITTING,
        TaskStatus.VALIDATING,
        TaskStatus.RENDERING,
        TaskStatus.SUCCESS,
    ]


@pytest.mark.asyncio
async def test_execute_provider_error_fails_without_switching_provider():
    failing = _Provider(error=ProviderResponseError("invalid result", code="DIAGRAM_SCHEMA_INVALID"))
    other = _Provider(
        submission=ProviderSubmission(status="succeeded", result=_diagram())
    )
    registry = _registry(failing)
    task = _task()
    session = _Session(task)
    schedule_execute = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=registry,
        schedule_execute=schedule_execute,
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    await engine.execute(task.id)

    assert failing.submit_calls == 1
    assert other.submit_calls == 0
    assert task.status == TaskStatus.FAILED.value
    assert task.error_code == "DIAGRAM_SCHEMA_INVALID"
    assert task.error_message == "生成结果不符合流程图规则，请重新描述流程后再试"
    schedule_execute.assert_not_called()


@pytest.mark.asyncio
async def test_execute_async_provider_schedules_bounded_poll_and_then_succeeds():
    clock = [datetime(2026, 8, 17, 12, 0, 1)]
    provider = _Provider(
        submission=ProviderSubmission(
            provider_request_id="request-async",
            mode="async",
            status="queued",
        ),
        poll_results=[
            ProviderPollResult(status="processing"),
            ProviderPollResult(status="succeeded", result=_diagram()),
        ],
    )
    task = _task()
    session = _Session(task)
    schedule_poll = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=_registry(provider),
        schedule_poll=schedule_poll,
        now=lambda: clock[0],
    )

    await engine.execute(task.id)
    assert task.status == TaskStatus.PROVIDER_QUEUED.value
    schedule_poll.assert_called_once_with(task.id, 3)

    clock[0] += timedelta(seconds=3)
    await engine.poll(task.id)
    assert task.status == TaskStatus.PROVIDER_PROCESSING.value
    assert schedule_poll.call_args_list[-1].args == (task.id, 6)

    clock[0] += timedelta(seconds=6)
    await engine.poll(task.id)
    assert provider.poll_calls == 2
    assert task.status == TaskStatus.SUCCESS.value
    assert task.poll_count == 2


@pytest.mark.asyncio
async def test_retryable_submit_error_keeps_task_and_requeues_same_provider():
    clock = [datetime(2026, 8, 17, 12, 0, 1)]
    provider = _Provider(error=ProviderHTTPError(503))
    task = _task()
    session = _Session(task)
    schedule_execute = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=_registry(provider),
        schedule_execute=schedule_execute,
        now=lambda: clock[0],
    )

    await engine.execute(task.id)

    assert task.status == TaskStatus.SUBMITTING.value
    assert task.retry_count == 1
    assert task.next_poll_at == clock[0] + timedelta(seconds=3)
    schedule_execute.assert_called_once_with(task.id, 3)


@pytest.mark.asyncio
async def test_cancel_provider_reaches_provider_and_marks_request_canceled():
    provider = _Provider()
    task = _task(
        status=TaskStatus.CANCELED.value,
        provider_request_id="request-cancel",
    )
    session = _Session(task)
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=_registry(provider),
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    await engine.cancel_provider(task.id)

    assert provider.cancel_calls == 1
    assert task.provider_status == "canceled"
    assert [call.operation for call in session.added] == ["cancel"]


@pytest.mark.asyncio
async def test_resume_rendering_task_completes_after_worker_restart():
    provider = _Provider()
    task = _task(status=TaskStatus.RENDERING.value)
    task.result = compile_diagram_document(_diagram()).model_dump(mode="json", by_alias=True)
    session = _Session(task)
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=_registry(provider),
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    await engine.resume(task.id)

    assert task.status == TaskStatus.SUCCESS.value
    assert task.result["mermaidSource"].startswith("flowchart TB")


@pytest.mark.asyncio
async def test_compensate_resumes_validation_and_rendering_tasks():
    task = _task(status=TaskStatus.VALIDATING.value)
    task.result = _diagram()
    session = _Session(task)
    schedule_execute = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        schedule_execute=schedule_execute,
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    count = await engine.compensate()

    assert count == 1
    schedule_execute.assert_called_once_with(task.id, 0)


@pytest.mark.asyncio
async def test_execute_expired_task_reaches_failed_without_provider_call():
    provider = _Provider(submission=ProviderSubmission(status="succeeded", result=_diagram()))
    task = _task(deadline=datetime(2026, 8, 17, 11, 59, 59))
    session = _Session(task)
    schedule_cancel = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=_registry(provider),
        schedule_cancel=schedule_cancel,
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    await engine.execute(task.id)

    assert provider.submit_calls == 0
    assert task.status == TaskStatus.FAILED.value
    assert task.error_code == "PROVIDER_TASK_TIMEOUT"
    schedule_cancel.assert_not_called()


@pytest.mark.asyncio
async def test_poll_expired_task_schedules_best_effort_provider_cancel():
    provider = _Provider(poll_results=[ProviderPollResult(status="processing")])
    task = _task(
        status=TaskStatus.PROVIDER_PROCESSING.value,
        deadline=datetime(2026, 8, 17, 11, 59, 59),
        provider_request_id="request-timeout",
    )
    session = _Session(task)
    schedule_cancel = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        registry=_registry(provider),
        schedule_cancel=schedule_cancel,
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    await engine.poll(task.id)

    assert provider.poll_calls == 0
    assert task.status == TaskStatus.FAILED.value
    schedule_cancel.assert_called_once_with(task.id, 0)


@pytest.mark.asyncio
async def test_compensate_requeues_waiting_task():
    task = _task()
    session = _Session(task)
    schedule_execute = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        schedule_execute=schedule_execute,
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    count = await engine.compensate()

    assert count == 1
    schedule_execute.assert_called_once_with(task.id, 0)


@pytest.mark.asyncio
async def test_compensate_expires_stale_unsubmitted_generation_task():
    now = datetime(2026, 8, 17, 12, 0, 1)
    task = _task()
    task.created_at = now - timedelta(hours=1, microseconds=1)
    session = _Session(task)
    publisher = AsyncMock()
    schedule_execute = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        event_publisher=publisher,
        schedule_execute=schedule_execute,
        now=lambda: now,
    )

    count = await engine.compensate()

    assert count == 1
    assert task.status == TaskStatus.EXPIRED.value
    assert task.progress == 5
    assert task.stage == "任务已过期"
    assert task.error_code == "TASK_EXPIRED"
    assert task.error_message == "任务已过期，请重新生成"
    schedule_execute.assert_not_called()
    assert publisher.await_args.args[0].status is TaskStatus.EXPIRED


@pytest.mark.asyncio
async def test_compensate_keeps_generation_task_at_one_hour_boundary_recoverable():
    now = datetime(2026, 8, 17, 12, 0, 1)
    task = _task()
    task.created_at = now - timedelta(hours=1)
    session = _Session(task)
    schedule_execute = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        schedule_execute=schedule_execute,
        now=lambda: now,
    )

    count = await engine.compensate()

    assert count == 1
    assert task.status == TaskStatus.WAITING.value
    schedule_execute.assert_called_once_with(task.id, 0)


@pytest.mark.asyncio
async def test_compensate_expires_stale_submitting_task_and_cancels_known_provider_request():
    now = datetime(2026, 8, 17, 12, 0, 1)
    task = _task(status=TaskStatus.SUBMITTING.value, provider_request_id="request-zombie")
    task.created_at = now - timedelta(hours=2)
    session = _Session(task)
    schedule_cancel = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        schedule_cancel=schedule_cancel,
        now=lambda: now,
    )

    count = await engine.compensate()

    assert count == 1
    assert task.status == TaskStatus.EXPIRED.value
    schedule_cancel.assert_called_once_with(task.id, 0)


@pytest.mark.asyncio
async def test_compensate_retries_cancel_for_expired_task_with_provider_request():
    task = _task(
        status=TaskStatus.EXPIRED.value,
        provider_request_id="request-zombie",
    )
    session = _Session(task)
    schedule_cancel = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        schedule_cancel=schedule_cancel,
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    count = await engine.compensate()

    assert count == 1
    schedule_cancel.assert_called_once_with(task.id, 0)


@pytest.mark.asyncio
async def test_compensate_keeps_stale_export_task_for_export_worker_recovery():
    now = datetime(2026, 8, 17, 12, 0, 1)
    task = _task(task_type=TaskType.DIAGRAM_EXPORT.value)
    task.created_at = now - timedelta(hours=2)
    session = _Session(task)
    schedule_export = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        schedule_export=schedule_export,
        now=lambda: now,
    )

    count = await engine.compensate()

    assert count == 1
    assert task.status == TaskStatus.WAITING.value
    schedule_export.assert_called_once_with(task.id)


@pytest.mark.asyncio
async def test_compensate_requeues_export_task_to_chromium_worker():
    task = _task(
        task_type=TaskType.DIAGRAM_EXPORT.value,
        status=TaskStatus.RENDERING.value,
        deadline=datetime(2026, 8, 17, 11, 59, 59),
    )
    session = _Session(task)
    schedule_execute = Mock()
    schedule_export = Mock()
    engine = TaskEngine(
        session_factory=_session_factory(session),
        schedule_execute=schedule_execute,
        schedule_export=schedule_export,
        now=lambda: datetime(2026, 8, 17, 12, 0, 1),
    )

    count = await engine.compensate()

    assert count == 1
    assert task.status == TaskStatus.RENDERING.value
    schedule_execute.assert_not_called()
    schedule_export.assert_called_once_with(task.id)
