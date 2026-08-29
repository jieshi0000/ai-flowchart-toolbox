from __future__ import annotations

import math
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.base import CamelVO

MAX_DIAGRAM_NODES = 50
MAX_DIAGRAM_EDGES = 100
MAX_TITLE_LENGTH = 100
MAX_LABEL_LENGTH = 120

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_HTML_RE = re.compile(r"</?[A-Za-z][^>]*>")
_DANGEROUS_RE = re.compile(
    r"(?:<\s*script\b|(?:java|vb)script\s*:|data\s*:\s*text/html|on[a-z]+\s*=)",
    re.IGNORECASE,
)
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?$")


def _plain_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name}不能为空")
    if _HTML_RE.search(value) or _DANGEROUS_RE.search(value):
        raise ValueError(f"{field_name}不能包含 HTML、脚本或事件属性")
    if any(ord(ch) < 32 and ch not in "\r\n\t" for ch in value):
        raise ValueError(f"{field_name}不能包含控制字符")
    return value


class DiagramDirection(StrEnum):
    TB = "TB"
    LR = "LR"


class DiagramNodeType(StrEnum):
    START = "start"
    END = "end"
    PROCESS = "process"
    DECISION = "decision"
    INPUT_OUTPUT = "input_output"
    SUBPROCESS = "subprocess"


class DiagramSchema(CamelVO):
    model_config = ConfigDict(extra="forbid")


class DiagramPosition(DiagramSchema):
    x: float = 0
    y: float = 0

    @field_validator("x", "y")
    @classmethod
    def finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("节点坐标必须是有限数字")
        return value


class DiagramNodeStyle(DiagramSchema):
    fill: str | None = None
    stroke: str | None = None

    @field_validator("fill", "stroke")
    @classmethod
    def color(cls, value: str | None) -> str | None:
        if value is not None and not _COLOR_RE.fullmatch(value):
            raise ValueError("节点颜色仅支持 #RGB 或 #RRGGBB")
        return value.upper() if value else value


class DiagramNode(DiagramSchema):
    id: str = Field(min_length=1, max_length=64)
    type: DiagramNodeType
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    position: DiagramPosition = Field(default_factory=DiagramPosition)
    style: DiagramNodeStyle | None = None

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("节点 id 必须以字母开头，只能包含字母、数字、下划线和连字符")
        return value

    @field_validator("label")
    @classmethod
    def valid_label(cls, value: str) -> str:
        return _plain_text(value, "节点标签")


class DiagramEdge(DiagramSchema):
    id: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=MAX_LABEL_LENGTH)
    condition: str | None = Field(default=None, max_length=MAX_LABEL_LENGTH)

    @field_validator("id", "source", "target")
    @classmethod
    def valid_ref(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("连线 id 和节点引用格式无效")
        return value

    @field_validator("label", "condition")
    @classmethod
    def valid_text(cls, value: str | None) -> str | None:
        return _plain_text(value, "连线文本") if value is not None else None


class DiagramMetadata(DiagramSchema):
    generated_by: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=160)
    source_task_id: str | None = Field(default=None, max_length=64)
    theme: Literal["blue", "purple", "green"] | None = None
    version: int = Field(default=1, ge=1)


class DiagramGraph(DiagramSchema):
    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    direction: DiagramDirection = DiagramDirection.TB
    nodes: list[DiagramNode] = Field(default_factory=list, max_length=MAX_DIAGRAM_NODES)
    edges: list[DiagramEdge] = Field(default_factory=list, max_length=MAX_DIAGRAM_EDGES)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _plain_text(value, "文档标题")

    @model_validator(mode="after")
    def valid_graph(self) -> "DiagramGraph":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("节点 id 必须唯一")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("连线 id 必须唯一")
        known = set(node_ids)
        invalid = [edge.id for edge in self.edges if edge.source not in known or edge.target not in known]
        if invalid:
            raise ValueError(f"连线引用了不存在的节点: {', '.join(invalid)}")
        return self


class DiagramGenerationResult(DiagramGraph):
    """模型返回的流程图语义结构和可选 Mermaid 预览源码。

    ``nodes``、``edges`` 等 JSON 字段仍然是可编辑和持久化的权威数据。
    Mermaid 仅用于首次生成后的展示；服务端会在使用前进行受限校验，编辑
    保存后仍由权威 JSON 重新编译。
    """

    mermaid_source: str | None = Field(default=None, max_length=20_000)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "title": "DiagramGenerationResult",
        },
    )


class DiagramDocument(DiagramGraph):
    id: str | None = Field(default=None, max_length=64)
    mermaid_source: str = Field(default="", max_length=200_000)
    metadata: DiagramMetadata = Field(default_factory=DiagramMetadata)


class DiagramSaveRequest(DiagramGraph):
    """客户端可保存的语义字段；Mermaid 必须由服务端重新编译。"""

    version: int = Field(ge=1)


class DiagramTemplateConfig(DiagramGraph):
    metadata: dict[str, Any] = Field(default_factory=dict)
