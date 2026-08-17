from types import SimpleNamespace
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.api import task_api
from app.exceptions.business import BusinessException
from app.schemas.task import TaskCreateRequest, TaskCreateResponse, TaskStatus


def _request(user_id: str | None = "user-a", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/flowchart/tasks/create",
            "headers": headers or [],
        }
    )
    if user_id is not None:
        request.state.user_id = user_id
    return request


@pytest.mark.asyncio
async def test_create_endpoint_uses_authenticated_request_user(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_create_task(session, user_id, payload, **kwargs):
        captured["session"] = session
        captured["user_id"] = user_id
        captured["payload"] = payload
        captured["enqueue"] = kwargs["enqueue"]
        return TaskCreateResponse(task_id=uuid4(), status=TaskStatus.WAITING, estimated_seconds=30)

    monkeypatch.setattr(task_api, "create_task", fake_create_task)
    payload = TaskCreateRequest(prompt="审批流程", idempotencyKey="idem-1")
    session = SimpleNamespace()

    result = await task_api.create_flowchart_task(payload, _request(), session)

    assert result.code == 200
    assert captured["session"] is session
    assert captured["user_id"] == "user-a"
    assert captured["payload"] is payload


@pytest.mark.asyncio
async def test_create_endpoint_requires_authenticated_user(monkeypatch):
    monkeypatch.setattr(task_api, "get_settings", lambda: SimpleNamespace(auth=SimpleNamespace(enabled=True)))
    payload = TaskCreateRequest(prompt="审批流程", idempotencyKey="idem-1")

    with pytest.raises(BusinessException) as exc_info:
        await task_api.create_flowchart_task(payload, _request(user_id=None), SimpleNamespace())

    assert exc_info.value.code == 401


def test_current_user_uses_local_header_only_when_auth_is_disabled(monkeypatch):
    monkeypatch.setattr(task_api, "get_settings", lambda: SimpleNamespace(auth=SimpleNamespace(enabled=False)))

    user_id = task_api._current_user_id(
        _request(user_id=None, headers=[(b"x-flowchart-user-id", b"local-user-a")])
    )

    assert user_id == "local-user-a"
