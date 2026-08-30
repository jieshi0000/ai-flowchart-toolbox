import json
from uuid import uuid4

import pytest

from app.core.redis import close_redis, get_redis
from app.schemas.task import TaskStatus
from app.schemas.task_event import TaskStatusEvent
from app.services.event_service import publish_task_event, task_event_channel


@pytest.mark.asyncio
async def test_task_event_is_delivered_through_real_redis_pubsub():
    task_id = uuid4()
    event = TaskStatusEvent(
        taskId=task_id,
        status=TaskStatus.RENDERING,
        progress=90,
        stage="正在生成 Mermaid 和导出结果",
    )
    redis = get_redis()
    pubsub = redis.pubsub()
    channel = task_event_channel(task_id)
    try:
        await pubsub.subscribe(channel)
        # redis-py 的 subscribe 返回后，仍需消费服务端确认帧才算订阅已生效。
        await pubsub.get_message(timeout=1.0)
        await publish_task_event(event)
        message = None
        for _ in range(3):
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is not None:
                break

        assert message is not None
        assert message["type"] == "message"
        assert json.loads(message["data"]) == {
            "taskId": str(task_id),
            "status": "rendering",
            "progress": 90,
            "stage": "正在生成 Mermaid 和导出结果",
        }
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await close_redis()
