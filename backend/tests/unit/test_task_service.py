from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import pytest

from app.exceptions.business import BusinessException
from app.models.task import FlowchartTask
from app.providers.provider_registry import ProviderSelectionError
from app.schemas.task import TaskCreateRequest, TaskStatus
from app.services import task_service


@pytest.fixture(autouse=True)
def disable_default_task_event_publisher(monkeypatch):
    async def publish_nothing(_event):
        return None

    monkeypatch.setattr("app.services.task_service.publish_task_event", publish_nothing)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeSession:
    def __init__(self, *query_values):
        self._query_values = list(query_values)
        self.added: list[FlowchartTask] = []
        self.statements = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, statement):
        self.statements.append(statement)
        value = self._query_values.pop(0)
        if isinstance(value, int):
            return SimpleNamespace(rowcount=value)
        return _ScalarResult(value)

    def add(self, task):
        self.added.append(task)


def _registration():
    return SimpleNamespace(
        provider_id="provider-a",
        config=SimpleNamespace(model="model-a", task_timeout_seconds=600),
    )


def _registry():
    registry = Mock()
    registry.select.return_value = _registration()
    return registry


def _request(idempotency_key: str = "idem-1") -> TaskCreateRequest:
    return TaskCreateRequest(
        prompt="请假申请审批流程",
        direction="TB",
        detailLevel="standard",
        idempotencyKey=idempotency_key,
    )


def _task(
    *,
    user_id: str = "user-a",
    status: str = "waiting",
    session_id: str | None = "browser-session-a",
    idempotency_key: str = "idem-old",
    request_snapshot: dict | None = None,
) -> FlowchartTask:
    now = datetime.now(UTC).replace(tzinfo=None)
    return FlowchartTask(
        id=uuid4(),
        user_id=user_id,
        session_id=session_id,
        type="diagram_generate",
        status=status,
        progress=5,
        stage="任务已创建，等待处理",
        request_snapshot=request_snapshot
        or {
            "type": "diagram_generate",
            "prompt": "请假申请审批流程",
            "direction": "TB",
            "detail_level": "standard",
            "provider_id": None,
            "model": None,
        },
        provider_id="provider-a",
        model_name="model-a",
        idempotency_key=idempotency_key,
        poll_count=0,
        expires_at=now + timedelta(days=7),
    )


@pytest.mark.asyncio
async def test_create_task_persists_waiting_snapshot_and_selected_provider():
    session = FakeSession(None)
    registry = _registry()

    response = await task_service.create_task(session, "user-a", _request(), registry=registry)

    task = session.added[0]
    assert str(response.task_id) == str(task.id)
    assert response.status is TaskStatus.WAITING
    assert task.user_id == "user-a"
    assert task.status == TaskStatus.WAITING.value
    assert task.progress == 5
    assert task.provider_id == "provider-a"
    assert task.model_name == "model-a"
    assert task.request_snapshot["prompt"] == "请假申请审批流程"
    assert "idempotency_key" not in task.request_snapshot
    assert task.deadline_at is not None
    registry.select.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_task_publishes_waiting_event_after_commit():
    session = FakeSession(None)
    publisher = AsyncMock()

    await task_service.create_task(
        session,
        "user-a",
        _request(),
        registry=_registry(),
        event_publisher=publisher,
    )

    event = publisher.await_args.args[0]
    assert event.status is TaskStatus.WAITING
    assert event.stage == "任务已创建，等待处理"


@pytest.mark.asyncio
async def test_create_task_reuses_existing_idempotency_task_without_selecting_provider():
    existing = _task(status="provider_processing")
    session = FakeSession(existing)
    registry = _registry()

    response = await task_service.create_task(session, "user-a", _request("idem-old"), registry=registry)

    assert str(response.task_id) == str(existing.id)
    assert response.status is TaskStatus.PROVIDER_PROCESSING
    assert session.added == []
    registry.select.assert_not_called()


@pytest.mark.asyncio
async def test_get_task_rejects_non_owner():
    task = _task(user_id="user-a")
    session = FakeSession(task)

    with pytest.raises(BusinessException) as exc_info:
        await task_service.get_task(session, "user-b", task.id)

    assert exc_info.value.code == 403


@pytest.mark.asyncio
async def test_list_recoverable_tasks_is_scoped_to_session_when_requested():
    task = _task(status="provider_processing", session_id="browser-session-a")

    class SessionWithActiveTasks:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [task]))

    session = SessionWithActiveTasks()
    result = await task_service.list_recoverable_tasks(
        session,
        "user-a",
        session_id="browser-session-a",
    )

    assert [item.task_id for item in result] == [task.id]
    statement = str(session.statements[0])
    assert "flowchart_task.session_id" in statement
    assert "flowchart_task.user_id" in statement


@pytest.mark.asyncio
async def test_cancel_task_marks_local_task_canceled_without_provider_call():
    task = _task(status="waiting")
    session = FakeSession(task, 1)

    response = await task_service.cancel_task(session, "user-a", task.id)

    assert response.status is TaskStatus.CANCELED
    assert response.provider_cancel_requested is False
    assert "UPDATE flowchart_task" in str(session.statements[1])
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_task_publishes_committed_canceled_status():
    task = _task(status="waiting")
    session = FakeSession(task, 1)
    publisher = AsyncMock()

    await task_service.cancel_task(
        session,
        "user-a",
        task.id,
        event_publisher=publisher,
    )

    event = publisher.await_args.args[0]
    assert event.status is TaskStatus.CANCELED
    assert event.progress == 0
    assert event.error_code == "TASK_CANCELED"


@pytest.mark.asyncio
async def test_retry_creates_new_task_with_new_idempotency_key_and_source_snapshot():
    source = _task(status="failed")
    session = FakeSession(source, None)
    registry = _registry()

    response = await task_service.retry_task(session, "user-a", source.id, registry=registry)

    retried = session.added[0]
    assert response.source_task_id == source.id
    assert str(response.task_id) == str(retried.id)
    assert retried.idempotency_key != source.idempotency_key
    assert retried.request_snapshot["source_task_id"] == str(source.id)
    assert source.status == "failed"


@pytest.mark.asyncio
async def test_retry_preserves_deep_thinking_switch_from_source_snapshot():
    source = _task(
        status="failed",
        request_snapshot={
            "type": "diagram_generate",
            "prompt": "请假申请审批流程",
            "direction": "TB",
            "detail_level": "standard",
            "diagram_theme": "blue",
            "thinking_enabled": True,
            "provider_id": None,
            "model": None,
        },
    )
    session = FakeSession(source, None)

    await task_service.retry_task(session, "user-a", source.id, registry=_registry())

    assert session.added[0].request_snapshot["thinking_enabled"] is True


@pytest.mark.asyncio
async def test_create_task_maps_provider_selection_error_to_business_error_code():
    session = FakeSession(None)
    registry = _registry()
    registry.select.side_effect = ProviderSelectionError("PROVIDER_UNHEALTHY", "指定的供应商当前不可用")

    with pytest.raises(BusinessException) as exc_info:
        await task_service.create_task(session, "user-a", _request(), registry=registry)

    assert exc_info.value.code == 502
    assert exc_info.value.error_code == "PROVIDER_UNHEALTHY"
