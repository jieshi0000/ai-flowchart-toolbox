from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelVO
from app.schemas.task import TaskStatus


class ExportFormat(StrEnum):
    SVG = "SVG"
    PNG = "PNG"
    MERMAID = "MERMAID"
    JSON = "JSON"


class ExportBackground(StrEnum):
    TRANSPARENT = "transparent"
    WHITE = "white"


class ExportRequest(CamelVO):
    format: ExportFormat
    background: ExportBackground = ExportBackground.TRANSPARENT


class ExportTaskResponse(CamelVO):
    task_id: UUID
    status: TaskStatus = TaskStatus.WAITING
