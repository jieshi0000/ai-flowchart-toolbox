"""流程图任务事件的公开载荷。"""

from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelVO
from app.schemas.task import TaskStatus


class TaskStatusEvent(CamelVO):
    """通过 SSE 推送给任务所有者的最小状态快照。"""

    task_id: UUID
    status: TaskStatus
    progress: int = Field(ge=0, le=100)
    stage: str | None = None
    document_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None


__all__ = ["TaskStatusEvent"]
