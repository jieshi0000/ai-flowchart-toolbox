from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.schemas.diagram import DiagramDocument, DiagramGraph


def validate_diagram_document(payload: DiagramGraph | Mapping[str, Any]) -> DiagramDocument:
    """Normalize and validate a diagram payload through the authoritative schema."""
    if isinstance(payload, DiagramGraph):
        payload = payload.model_dump(mode="python")
    return DiagramDocument.model_validate(payload)
