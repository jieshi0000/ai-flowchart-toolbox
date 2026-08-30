from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.schemas.diagram import (
    DiagramDirection,
    DiagramDocument,
    DiagramEdge,
    DiagramGraph,
    DiagramNode,
    DiagramNodeType,
)


_MERMAID_ESCAPE_MAP = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
    "[": "&#91;",
    "]": "&#93;",
    "{": "&#123;",
    "}": "&#125;",
    "(": "&#40;",
    ")": "&#41;",
    "|": "&#124;",
    "/": "&#47;",
    "\\": "&#92;",
    "#": "&#35;",
    "%": "&#37;",
    ";": "&#59;",
    ":": "&#58;",
    "=": "&#61;",
    "`": "&#96;",
    "!": "&#33;",
}

MAX_MODEL_MERMAID_SOURCE_LENGTH = 20_000
_MODEL_MERMAID_DIRECTION_RE = re.compile(r"^\s*flowchart\s+(TB|LR)\s*$", re.IGNORECASE)
_UNSAFE_MODEL_MERMAID_RE = re.compile(
    r"(?:<[^>]*>|(?:java|vb)script\s*:|data\s*:|on[a-z]+\s*=|%%\{|\bhref\b)",
    re.IGNORECASE,
)
_DISALLOWED_MODEL_MERMAID_STATEMENT_RE = re.compile(
    r"^\s*(?:click|style|classDef|class|linkStyle|accTitle|accDescr)\b",
    re.IGNORECASE,
)


def validate_diagram_document(payload: DiagramGraph | Mapping[str, Any]) -> DiagramDocument:
    """Normalize and validate a diagram payload through the authoritative schema."""
    if isinstance(payload, DiagramGraph):
        payload = payload.model_dump(mode="python")
    return DiagramDocument.model_validate(payload)


def compile_mermaid(payload: DiagramGraph | Mapping[str, Any]) -> str:
    """Compile a validated DiagramDocument into deterministic Mermaid source."""
    document = validate_diagram_document(payload)
    return _compile_valid_document(document)


def compile_diagram_document(payload: DiagramGraph | Mapping[str, Any]) -> DiagramDocument:
    """Return a validated document with Mermaid source regenerated from its graph data."""
    document = validate_diagram_document(payload)
    mermaid_source = _compile_valid_document(document)
    return document.model_copy(update={"mermaid_source": mermaid_source})


def compile_generated_diagram_document(payload: DiagramGraph | Mapping[str, Any]) -> DiagramDocument:
    """Validate an AI result and retain only a safe, direction-consistent Mermaid preview.

    The structured graph remains authoritative.  A model-provided Mermaid source is
    intentionally treated as a constrained display artifact: invalid, unsafe, overly
    long, or direction-mismatched source is replaced with the deterministic compiler
    output from the validated graph.
    """

    # 新增的可选 mermaidSource 在旧模型响应中可能缺失；Pydantic 将其
    # 序列化后会变成显式 null，而 DiagramDocument 的持久化字段是字符串。
    # 去掉空值即可沿用可靠的 JSON -> Mermaid 编译回退路径。
    if isinstance(payload, DiagramGraph):
        normalized_payload: Mapping[str, Any] = payload.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        )
    else:
        normalized_payload = dict(payload)
    normalized_payload = dict(normalized_payload)
    if normalized_payload.get("mermaidSource") is None:
        normalized_payload.pop("mermaidSource", None)
    if normalized_payload.get("mermaid_source") is None:
        normalized_payload.pop("mermaid_source", None)

    document = validate_diagram_document(normalized_payload)
    fallback_source = _compile_valid_document(document)
    model_source = _validated_model_mermaid_source(
        document.mermaid_source,
        document.direction,
        fallback_source,
    )
    return document.model_copy(update={"mermaid_source": model_source or fallback_source})


def _compile_valid_document(document: DiagramDocument) -> str:
    node_aliases = {node.id: f"n{index}" for index, node in enumerate(document.nodes)}
    lines = [f"flowchart {document.direction.value}"]
    lines.extend(_compile_node(node, node_aliases[node.id]) for node in document.nodes)
    lines.extend(_compile_edge(edge, node_aliases) for edge in document.edges)
    return "\n".join(lines)


def _validated_model_mermaid_source(
    value: str,
    direction: DiagramDirection,
    canonical_source: str,
) -> str | None:
    """Return a safe model Mermaid source, or ``None`` to trigger JSON fallback."""

    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized or len(normalized) > MAX_MODEL_MERMAID_SOURCE_LENGTH:
        return None
    if "\x00" in normalized or _UNSAFE_MODEL_MERMAID_RE.search(normalized):
        return None

    lines = normalized.split("\n")
    first_line = next((line for line in lines if line.strip()), "")
    match = _MODEL_MERMAID_DIRECTION_RE.fullmatch(first_line)
    if match is None or match.group(1).upper() != direction.value:
        return None
    if any(_DISALLOWED_MODEL_MERMAID_STATEMENT_RE.match(line) for line in lines):
        return None
    # Mermaid 没有可安全嵌入 Python Worker 的完整解析器。为确保每次展示都
    # 能被前端 Mermaid 解析，模型源码还必须精确对应已校验 JSON 的受限、
    # 确定性编译结果；模型若使用了别名、语法或标签的其他写法，统一回退。
    return normalized if normalized == canonical_source else None


def _compile_node(node: DiagramNode, mermaid_id: str) -> str:
    label = _escape_mermaid_text(node.label)
    if node.type in (DiagramNodeType.START, DiagramNodeType.END):
        return f'{mermaid_id}(["{label}"])'
    if node.type is DiagramNodeType.PROCESS:
        return f'{mermaid_id}["{label}"]'
    if node.type is DiagramNodeType.DECISION:
        return f'{mermaid_id}{{"{label}"}}'
    if node.type is DiagramNodeType.INPUT_OUTPUT:
        return f'{mermaid_id}[/"{label}"/]'
    if node.type is DiagramNodeType.SUBPROCESS:
        return f'{mermaid_id}[["{label}"]]'
    raise ValueError(f"Unsupported diagram node type: {node.type}")


def _compile_edge(edge: DiagramEdge, node_aliases: Mapping[str, str]) -> str:
    edge_text = edge.condition or edge.label
    if edge_text is None:
        return f"{node_aliases[edge.source]} --> {node_aliases[edge.target]}"
    return f"{node_aliases[edge.source]} -->|{_escape_mermaid_text(edge_text)}| {node_aliases[edge.target]}"


def _escape_mermaid_text(value: str) -> str:
    normalized = " ".join(value.split())
    return "".join(_MERMAID_ESCAPE_MAP.get(char, char) for char in normalized)
