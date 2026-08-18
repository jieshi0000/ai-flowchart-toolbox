import uuid

import asyncpg
import pytest

from tests.conftest import DB_URL


@pytest.fixture
async def reset_flowchart_tasks():
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("TRUNCATE TABLE flowchart_task")
        yield
    finally:
        await conn.execute("TRUNCATE TABLE flowchart_task")
        await conn.close()


def _headers(user_id: str) -> dict[str, str]:
    return {"X-Flowchart-User-Id": user_id}


async def _create_task(
    client,
    user_id: str,
    idempotency_key: str,
    session_id: str = "browser-session-a",
) -> dict:
    response = await client.post(
        "/api/flowchart/tasks/create",
        headers=_headers(user_id),
        json={
            "type": "diagram_generate",
            "prompt": "员工提交请假申请，主管审批后通知员工",
            "direction": "TB",
            "detailLevel": "standard",
            "sessionId": session_id,
            "idempotencyKey": idempotency_key,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["errorCode"] is None
    return body["data"]


async def test_task_creation_is_idempotent_and_scoped_to_the_user(client, reset_flowchart_tasks):
    idempotency_key = str(uuid.uuid4())
    first = await _create_task(client, "user-a", idempotency_key)
    duplicate = await _create_task(client, "user-a", idempotency_key)

    assert first["taskId"] == duplicate["taskId"]
    assert first["status"] == "waiting"

    own_response = await client.get(
        f"/api/flowchart/tasks/get?taskId={first['taskId']}",
        headers=_headers("user-a"),
    )
    assert own_response.json()["data"]["providerId"] == "deepseek-official-chat"

    other_response = await client.get(
        f"/api/flowchart/tasks/get?taskId={first['taskId']}",
        headers=_headers("user-b"),
    )
    assert other_response.json()["code"] == 403


async def test_task_cancel_and_retry_create_a_new_task(client, reset_flowchart_tasks):
    source = await _create_task(client, "user-a", str(uuid.uuid4()))

    canceled = await client.post(
        f"/api/flowchart/tasks/cancel?taskId={source['taskId']}",
        headers=_headers("user-a"),
    )
    canceled_body = canceled.json()
    assert canceled_body["code"] == 200
    assert canceled_body["data"]["status"] == "canceled"
    assert canceled_body["data"]["providerCancelRequested"] is False

    retried = await client.post(
        f"/api/flowchart/tasks/retry?taskId={source['taskId']}",
        headers=_headers("user-a"),
    )
    retried_body = retried.json()
    assert retried_body["code"] == 200
    assert retried_body["data"]["sourceTaskId"] == source["taskId"]
    assert retried_body["data"]["taskId"] != source["taskId"]


async def test_task_prompt_validation_returns_business_error_code(client, reset_flowchart_tasks):
    response = await client.post(
        "/api/flowchart/tasks/create",
        headers=_headers("user-a"),
        json={"prompt": "   ", "idempotencyKey": str(uuid.uuid4())},
    )

    body = response.json()
    assert body["code"] == 400
    assert body["errorCode"] == "PROMPT_EMPTY"


async def test_task_recovery_is_limited_to_the_current_user_and_optional_session(
    client,
    reset_flowchart_tasks,
):
    own_session_a = await _create_task(
        client,
        "user-a",
        str(uuid.uuid4()),
        session_id="browser-session-a",
    )
    own_session_b = await _create_task(
        client,
        "user-a",
        str(uuid.uuid4()),
        session_id="browser-session-b",
    )
    await _create_task(
        client,
        "user-b",
        str(uuid.uuid4()),
        session_id="browser-session-a",
    )

    session_response = await client.get(
        "/api/flowchart/tasks/list?sessionId=browser-session-a",
        headers=_headers("user-a"),
    )
    session_body = session_response.json()
    assert session_body["code"] == 200
    assert [task["taskId"] for task in session_body["data"]] == [own_session_a["taskId"]]

    user_response = await client.get(
        "/api/flowchart/tasks/list?limit=10",
        headers=_headers("user-a"),
    )
    user_body = user_response.json()
    assert user_body["code"] == 200
    assert {task["taskId"] for task in user_body["data"]} == {
        own_session_a["taskId"],
        own_session_b["taskId"],
    }

    invalid_session_response = await client.get(
        "/api/flowchart/tasks/list?sessionId=contains%20spaces",
        headers=_headers("user-a"),
    )
    invalid_session_body = invalid_session_response.json()
    assert invalid_session_body["code"] == 400
