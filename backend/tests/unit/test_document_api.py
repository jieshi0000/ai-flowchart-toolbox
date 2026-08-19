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
from app.schemas.export import ExportFormat, ExportRequest, ExportTaskResponse
from app.schemas.task import TaskStatus
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


@pytest.mark.asyncio
async def test_export_endpoint_passes_chromium_scheduler(monkeypatch):
    document_id = uuid4()
    captured = {}

    async def fake_export(*args, **kwargs):
        captured["args"] = args
        captured["schedule_render"] = kwargs["schedule_render"]
        return ExportTaskResponse(task_id=uuid4(), status=TaskStatus.WAITING)

    monkeypatch.setattr(document_api, "create_document_export", fake_export)

    result = await document_api.export_flowchart_document(
        ExportRequest(format=ExportFormat.SVG),
        _request(),
        document_id,
        SimpleNamespace(),
    )

    assert result.code == 200
    assert captured["args"][1] == "user-a"
    assert captured["args"][2] == document_id
    assert captured["schedule_render"] is document_api._enqueue_document_export
