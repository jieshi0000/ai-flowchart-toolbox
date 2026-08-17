from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import CamelVO


class TaskType(StrEnum):
    DIAGRAM_GENERATE = "diagram_generate"
    DIAGRAM_EXPORT = "diagram_export"


class TaskStatus(StrEnum):
    WAITING = "waiting"
    SUBMITTING = "submitting"
    PROVIDER_QUEUED = "provider_queued"
    PROVIDER_PROCESSING = "provider_processing"
    VALIDATING = "validating"
    RENDERING = "rendering"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    EXPIRED = "expired"


TERMINAL_TASK_STATUSES = frozenset({TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELED, TaskStatus.EXPIRED})


class DetailLevel(StrEnum):
    CONCISE = "concise"
    STANDARD = "standard"
    DETAILED = "detailed"


class TaskCreateRequest(CamelVO):
    type: TaskType = TaskType.DIAGRAM_GENERATE
    prompt: str = Field(min_length=1, max_length=4000)
    direction: str = Field(default="TB", pattern="^(TB|LR)$")
    detail_level: DetailLevel = DetailLevel.STANDARD
    provider_id: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("prompt")
    @classmethod
    def trim_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("流程描述不能为空")
        return value

    @field_validator("provider_id", "model")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("idempotency_key")
    @classmethod
    def trim_idempotency_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("幂等键不能为空")
        return value


class TaskCreateResponse(CamelVO):
    task_id: UUID
    status: TaskStatus = TaskStatus.WAITING
    estimated_seconds: int | None = Field(default=None, ge=0)


class TaskStatusResponse(CamelVO):
    task_id: UUID
    type: TaskType
    status: TaskStatus
    progress: int = Field(ge=0, le=100)
    stage: str | None = None
    provider_id: str | None = None
    model_name: str | None = None
    poll_count: int = Field(default=0, ge=0)
    document_id: UUID | None = None
    download_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class TaskCancelResponse(CamelVO):
    task_id: UUID
    status: TaskStatus = TaskStatus.CANCELED
    provider_cancel_requested: bool = False


class TaskRetryResponse(CamelVO):
    task_id: UUID
    source_task_id: UUID
    status: TaskStatus = TaskStatus.WAITING
