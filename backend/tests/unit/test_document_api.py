from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api import document_api
from app.exceptions.business import BusinessException
from app.exceptions.handlers import register_exception_handlers
from app.schemas.diagram import DiagramSaveRequest
from app.schemas.document import (
    DocumentDeleteResponse,
    FlowchartDocumentHistoryItem,
    FlowchartDocumentHistoryPage,
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


def _client(monkeypatch) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(document_api.router, prefix="/api")

    async def fake_session():
        yield SimpleNamespace()

    app.dependency_overrides[document_api.get_session] = fake_session
    monkeypatch.setattr(
        document_api,
        "current_flowchart_user_id",
        lambda _request: "user-a",
    )
    return TestClient(app)


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


def test_list_endpoint_returns_document_summaries(monkeypatch):
    document_id = uuid4()

    async def fake_list(*_args, **_kwargs):
        return FlowchartDocumentHistoryPage(
            records=[
                FlowchartDocumentHistoryItem(
                    id=document_id,
                    title="审批流程",
                    direction="TB",
                    created_at=datetime(2026, 8, 20, 10, 0, 0),
                    updated_at=datetime(2026, 8, 21, 10, 0, 0),
                )
            ],
            offset=0,
            limit=20,
            has_more=True,
        )

    monkeypatch.setattr(document_api, "list_documents", fake_list)

    with _client(monkeypatch) as client:
        response = client.get("/api/flowchart/documents/list?offset=0&limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["records"] == [
        {
            "id": str(document_id),
            "title": "审批流程",
            "direction": "TB",
            "createdAt": "2026-08-20 10:00:00",
            "updatedAt": "2026-08-21 10:00:00",
        }
    ]
    assert payload["data"]["hasMore"] is True


def test_delete_endpoint_returns_deleted_document_id(monkeypatch):
    document_id = uuid4()

    async def fake_delete(*_args, **_kwargs):
        return DocumentDeleteResponse(document_id=document_id)

    monkeypatch.setattr(document_api, "delete_document", fake_delete)

    with _client(monkeypatch) as client:
        response = client.post(
            "/api/flowchart/documents/delete",
            params={"documentId": str(document_id)},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"] == {"documentId": str(document_id)}


@pytest.mark.parametrize("code", [404, 403, 409])
def test_delete_endpoint_returns_business_error_codes(monkeypatch, code):
    async def fake_delete(*_args, **_kwargs):
        raise BusinessException(code=code, message="删除失败")

    monkeypatch.setattr(document_api, "delete_document", fake_delete)

    with _client(monkeypatch) as client:
        response = client.post(
            "/api/flowchart/documents/delete",
            params={"documentId": str(uuid4())},
        )

    assert response.status_code == 200
    assert response.json()["code"] == code
