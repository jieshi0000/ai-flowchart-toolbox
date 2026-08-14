from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.schemas.diagram import DiagramDocument, DiagramEdge, DiagramGraph, DiagramNode, DiagramNodeType


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


def _compile_valid_document(document: DiagramDocument) -> str:
    node_aliases = {node.id: f"n{index}" for index, node in enumerate(document.nodes)}
    lines = [f"flowchart {document.direction.value}"]
    lines.extend(_compile_node(node, node_aliases[node.id]) for node in document.nodes)
    lines.extend(_compile_edge(edge, node_aliases) for edge in document.edges)
    return "\n".join(lines)


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
