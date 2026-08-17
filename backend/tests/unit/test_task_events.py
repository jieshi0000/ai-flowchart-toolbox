import json
from uuid import uuid4

import pytest

from app.schemas.task import TaskStatus
from app.schemas.task_event import TaskStatusEvent
from app.services.event_service import (
    publish_task_event,
    stream_task_events,
    task_event_channel,
)


class _Redis:
    def __init__(self):
        self.published = []

    async def publish(self, channel, payload):
        self.published.append((channel, payload))


class _PubSub:
    def __init__(self, messages):
        self.messages = list(messages)
        self.subscribed = []
        self.unsubscribed = []
        self.closed = False

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def aclose(self):
        self.closed = True

    async def get_message(self, **_kwargs):
        return self.messages.pop(0) if self.messages else None


class _RedisWithPubSub(_Redis):
    def __init__(self, pubsub):
        super().__init__()
        self._pubsub = pubsub

    def pubsub(self):
        return self._pubsub


@pytest.mark.asyncio
async def test_publish_task_event_uses_namespaced_channel_and_public_payload():
    event = TaskStatusEvent(
        taskId=uuid4(),
        status=TaskStatus.VALIDATING,
        progress=75,
        stage="正在校验流程图结构",
    )
    redis = _Redis()

    await publish_task_event(event, redis_client=redis)

    channel, payload = redis.published[0]
    assert channel == task_event_channel(event.task_id)
    assert json.loads(payload) == {
        "taskId": str(event.task_id),
        "status": "validating",
        "progress": 75,
        "stage": "正在校验流程图结构",
    }
    assert "providerRequestId" not in payload


@pytest.mark.asyncio
async def test_stream_task_events_stops_after_terminal_event_and_closes_subscription():
    task_id = uuid4()
    initial = TaskStatusEvent(
        taskId=task_id,
        status=TaskStatus.PROVIDER_PROCESSING,
        progress=55,
        stage="模型正在生成流程图",
    )
    terminal = TaskStatusEvent(
        taskId=task_id,
        status=TaskStatus.SUCCESS,
        progress=100,
        stage="流程图已生成",
        documentId=uuid4(),
    )
    pubsub = _PubSub(
        [{"type": "message", "data": terminal.model_dump_json(by_alias=True)}]
    )
    redis = _RedisWithPubSub(pubsub)

    frames = [frame async for frame in stream_task_events(task_id, initial, redis_client=redis)]

    assert len(frames) == 2
    assert '"status":"provider_processing"' in frames[0]
    assert '"status":"success"' in frames[1]
    assert pubsub.subscribed == [task_event_channel(task_id)]
    assert pubsub.unsubscribed == [task_event_channel(task_id)]
    assert pubsub.closed is True
