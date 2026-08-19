from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from starlette.requests import Request

from app.api import document_api
from app.schemas.diagram import DiagramSaveRequest
from app.schemas.document import (
    FlowchartDocumentResponse,
    MermaidCompilation,
    MermaidCompilationState,
)
from app.services.document_service import DocumentVersionConflict


def _request(user_id: str = "user-a") -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/flowchart/documents/save",
            "headers": [],
        }
    )
    request.state.user_id = user_id
    return request


def _document(document_id: str) -> FlowchartDocumentResponse:
    return FlowchartDocumentResponse.model_validate(
        {
            "id": document_id,
            "title": "审批流程",
            "direction": "TB",
            "nodes": [],
            "edges": [],
            "mermaidSource": "flowchart TB",
            "metadata": {"version": 2},
            "mermaidCompilation": MermaidCompilation(
                version=2,
                status=MermaidCompilationState.READY,
            ).model_dump(mode="json", by_alias=True),
        }
    )


@pytest.mark.asyncio
async def test_save_endpoint_returns_latest_document_on_version_conflict(monkeypatch):
    document_id = str(uuid4())

    async def conflict(*_args, **_kwargs):
        raise DocumentVersionConflict(_document(document_id))

    monkeypatch.setattr(document_api, "save_document", conflict)
    payload = DiagramSaveRequest(
        version=1,
        title="审批流程",
        direction="TB",
        nodes=[],
        edges=[],
    )

    result = await document_api.save_flowchart_document(
        payload,
        _request(),
        UUID(document_id),
        SimpleNamespace(),
    )

    assert result.code == 409
    assert result.error_code == "DOCUMENT_VERSION_CONFLICT"
    assert result.data is not None
    assert result.data.latest_document is not None
    assert result.data.latest_document.id == document_id
