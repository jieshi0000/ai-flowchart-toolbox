from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelVO
from app.schemas.diagram import DiagramDocument


class MermaidCompilationState(StrEnum):
    IDLE = "idle"
    COMPILING = "compiling"
    READY = "ready"
    FAILED = "failed"


class MermaidCompilation(CamelVO):
    version: int = Field(ge=1)
    status: MermaidCompilationState
    error_code: str | None = None
    error_message: str | None = None


class FlowchartDocumentResponse(DiagramDocument):
    """文档读取模型；Mermaid 仅为服务端最近一次成功的派生结果。"""

    mermaid_compilation: MermaidCompilation


class DocumentSaveResponse(CamelVO):
    document_id: UUID
    version: int = Field(ge=1)
    mermaid_source: str = ""
    mermaid_compilation: MermaidCompilation
    latest_document: FlowchartDocumentResponse | None = None
