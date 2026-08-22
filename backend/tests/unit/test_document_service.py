from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.exceptions.business import BusinessException
from app.models.document import FlowchartDocument
from app.models.event import FlowchartEvent
from app.models.file import FlowchartFile
from app.models.provider_call import FlowchartProviderCall
from app.models.task import FlowchartTask
from app.schemas.diagram import DiagramSaveRequest
from app.schemas.document import MermaidCompilationState
from app.schemas.export import ExportFormat, ExportRequest
from app.schemas.task import TaskStatus, TaskType
from app.services import document_service


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if self._value is None:
            return []
        return self._value if isinstance(self._value, list) else [self._value]


class _Session:
    def __init__(self, *query_values):
        self._query_values = list(query_values)
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        value = self._query_values.pop(0)
        if isinstance(value, int):
            return SimpleNamespace(rowcount=value)
        return _ScalarResult(value)

    def add(self, value):
        self.added.append(value)

    async def delete(self, value):
        self.deleted.append(value)


def _session_factory(session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


def _document(*, version: int = 1, mermaid_source: str = "flowchart TB\nn0[\"开始\"]"):
    now = datetime.now(UTC).replace(tzinfo=None)
    document = FlowchartDocument(
        id=uuid4(),
        user_id="user-a",
        title="审批流程",
        direction="TB",
        diagram_data={
            "title": "审批流程",
            "direction": "TB",
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "label": "开始",
                    "position": {"x": 0, "y": 0},
                },
                {
                    "id": "end",
                    "type": "end",
                    "label": "结束",
                    "position": {"x": 0, "y": 120},
                },
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
            "metadata": {"version": version, "model": "model-a"},
        },
        mermaid_source=mermaid_source,
        version=version,
        source_task_id=uuid4(),
        expires_at=now + timedelta(days=30),
    )
    document.created_at = now - timedelta(minutes=1)
    document.updated_at = now
    return document


def _save_request(*, version: int = 1):
    return DiagramSaveRequest(
        version=version,
        title="审批流程（已编辑）",
        direction="TB",
        nodes=[
            {
                "id": "start",
                "type": "start",
                "label": "开始",
                "position": {"x": 20, "y": 20},
            },
            {
                "id": "end",
                "type": "end",
                "label": "结束",
                "position": {"x": 20, "y": 180},
            },
        ],
        edges=[{"id": "e1", "source": "start", "target": "end"}],
    )


@pytest.mark.asyncio
async def test_save_document_updates_authoritative_data_before_scheduling_mermaid():
    document = _document()
    session = _Session(document, 1)
    scheduler = Mock()

    result = await document_service.save_document(
        session,
        "user-a",
        document.id,
        _save_request(),
        schedule_compilation=scheduler,
    )

    assert result.version == 2
    assert result.mermaid_source == document.mermaid_source
    assert result.mermaid_compilation.status is MermaidCompilationState.COMPILING
    assert session.commit.await_count == 1
    event = session.added[0]
    assert isinstance(event, FlowchartEvent)
    assert event.payload == {"version": 2, "status": "compiling"}
    statement = str(session.statements[1])
    assert "flowchart_document.version" in statement
    scheduler.assert_called_once_with(document.id, 2)


@pytest.mark.asyncio
async def test_save_document_conflict_returns_latest_document_without_writing():
    document = _document(version=3)
    session = _Session(document, None)

    with pytest.raises(document_service.DocumentVersionConflict) as exc_info:
        await document_service.save_document(
            session,
            "user-a",
            document.id,
            _save_request(version=2),
        )

    assert exc_info.value.document.metadata.version == 3
    assert exc_info.value.document.mermaid_source == document.mermaid_source
    assert session.added == []
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_mermaid_compilation_updates_only_the_current_version(monkeypatch):
    document = _document(version=2, mermaid_source="old source")
    session = _Session(document, document)
    monkeypatch.setattr(document_service, "compile_mermaid", lambda _payload: "new source")

    await document_service.compile_document_mermaid(
        document.id,
        2,
        session_factory=_session_factory(session),
    )

    assert document.mermaid_source == "new source"
    assert session.commit.await_count == 1
    event = session.added[0]
    assert event.payload == {"version": 2, "status": "ready"}


@pytest.mark.asyncio
async def test_async_mermaid_failure_preserves_saved_document_data(monkeypatch):
    document = _document(version=2, mermaid_source="last successful source")
    original_data = dict(document.diagram_data)
    session = _Session(document, document)

    def fail_compile(_payload):
        raise ValueError("invalid mermaid")

    monkeypatch.setattr(document_service, "compile_mermaid", fail_compile)

    await document_service.compile_document_mermaid(
        document.id,
        2,
        session_factory=_session_factory(session),
    )

    assert document.mermaid_source == "last successful source"
    assert document.diagram_data == original_data
    event = session.added[0]
    assert event.payload == {"version": 2, "status": "failed"}


@pytest.mark.asyncio
async def test_async_mermaid_compilation_ignores_stale_version(monkeypatch):
    document = _document(version=3, mermaid_source="latest source")
    session = _Session(document)
    compiler = Mock(return_value="must not compile")
    monkeypatch.setattr(document_service, "compile_mermaid", compiler)

    await document_service.compile_document_mermaid(
        document.id,
        2,
        session_factory=_session_factory(session),
    )

    assert document.mermaid_source == "latest source"
    assert session.added == []
    session.commit.assert_not_awaited()
    compiler.assert_not_called()


class _Storage:
    def __init__(self):
        self.put_bytes = AsyncMock()
        self.remove = AsyncMock()


@pytest.mark.asyncio
async def test_mermaid_export_stores_server_generated_content_with_owned_record():
    document = _document()
    session = _Session(document, None)
    storage = _Storage()

    result = await document_service.create_document_export(
        session,
        "user-a",
        document.id,
        ExportRequest(format=ExportFormat.MERMAID),
        storage=storage,
    )

    assert result.status is TaskStatus.SUCCESS
    stored_path, content = storage.put_bytes.await_args.args[:2]
    storage_segments = stored_path.split("/")
    assert storage_segments[0] == "export"
    assert storage_segments[1].isdigit() and len(storage_segments[1]) == 8
    assert storage_segments[2] == "user-a"
    assert storage_segments[3] == str(document.id)
    assert content == document.mermaid_source.encode("utf-8")
    flowchart_file = next(item for item in session.added if isinstance(item, FlowchartFile))
    export_task = next(item for item in session.added if isinstance(item, FlowchartTask))
    assert flowchart_file.user_id == "user-a"
    assert flowchart_file.format == "MERMAID"
    assert str(export_task.document_id) == str(document.id)
    assert str(export_task.output_file_id) == str(flowchart_file.id)
    assert str(flowchart_file.task_id) == str(export_task.id)
    assert flowchart_file.expires_at - datetime.now(UTC).replace(tzinfo=None) < timedelta(hours=24, minutes=1)


@pytest.mark.asyncio
async def test_export_rejects_svg_until_d14():
    document = _document()
    session = _Session(document)

    with pytest.raises(BusinessException) as exc_info:
        await document_service.create_document_export(
            session,
            "user-a",
            document.id,
            ExportRequest(format=ExportFormat.SVG),
            storage=_Storage(),
        )

    assert exc_info.value.error_code == "EXPORT_FORMAT_UNSUPPORTED"


@pytest.mark.asyncio
async def test_list_documents_queries_current_users_recent_generated_documents_in_pages():
    now = datetime.now(UTC).replace(tzinfo=None)
    documents = []
    for index in range(21):
        document = _document()
        document.title = f"流程图 {index}"
        document.created_at = now - timedelta(days=1, minutes=index)
        document.updated_at = now - timedelta(minutes=index)
        documents.append(document)
    session = _Session(documents)

    page = await document_service.list_documents(
        session,
        "user-a",
        offset=0,
        limit=20,
        now=now,
    )

    assert [record.title for record in page.records] == [
        document.title for document in documents[:20]
    ]
    assert page.has_more is True
    statement = str(session.statements[0])
    assert "flowchart_document.user_id" in statement
    assert "flowchart_document.source_task_id IS NOT NULL" in statement
    assert "flowchart_document.expires_at >" in statement
    assert "ORDER BY flowchart_document.updated_at DESC, flowchart_document.id DESC" in statement
    assert 21 in session.statements[0].compile().params.values()


@pytest.mark.asyncio
async def test_export_creation_locks_document_against_concurrent_deletion():
    document = _document()
    session = _Session(document)

    await document_service.create_document_export(
        session,
        "user-a",
        document.id,
        ExportRequest(format=ExportFormat.SVG),
        schedule_render=Mock(),
    )

    assert "FOR UPDATE" in str(session.statements[0])


@pytest.mark.asyncio
async def test_delete_document_rejects_other_users_document():
    document = _document()
    session = _Session(document)

    with pytest.raises(BusinessException) as exc_info:
        await document_service.delete_document(session, "user-b", document.id, storage=_Storage())

    assert exc_info.value.code == 403
    assert session.deleted == []


@pytest.mark.asyncio
async def test_delete_document_blocks_pending_export_task():
    document = _document()
    pending_export = FlowchartTask(
        id=uuid4(),
        user_id="user-a",
        type=TaskType.DIAGRAM_EXPORT.value,
        status=TaskStatus.RENDERING.value,
        request_snapshot={},
        document_id=document.id,
        idempotency_key=str(uuid4()),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    session = _Session(document, [pending_export])

    with pytest.raises(BusinessException) as exc_info:
        await document_service.delete_document(session, "user-a", document.id, storage=_Storage())

    assert exc_info.value.code == 409
    assert exc_info.value.error_code == "DOCUMENT_DELETE_BLOCKED"
    assert session.deleted == []
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_document_keeps_database_records_when_object_deletion_fails():
    document = _document()
    file = FlowchartFile(
        id=uuid4(),
        user_id="user-a",
        document_id=document.id,
        original_name="审批流程.svg",
        stored_path="export/approval.svg",
        file_size=4,
        mime_type="image/svg+xml",
        format="SVG",
        file_role="export",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )
    session = _Session(document, [], [], [file])
    storage = _Storage()
    storage.remove.return_value = False

    with pytest.raises(BusinessException) as exc_info:
        await document_service.delete_document(session, "user-a", document.id, storage=storage)

    assert exc_info.value.code == 503
    assert exc_info.value.error_code == "DOCUMENT_DELETE_STORAGE_FAILED"
    assert session.deleted == []
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_document_clears_related_records_and_export_object():
    now = datetime.now(UTC).replace(tzinfo=None)
    document = _document()
    source_task = FlowchartTask(
        id=document.source_task_id,
        user_id="user-a",
        type=TaskType.DIAGRAM_GENERATE.value,
        status=TaskStatus.SUCCESS.value,
        request_snapshot={},
        result={"diagramData": "snapshot"},
        document_id=document.id,
        idempotency_key=str(uuid4()),
        expires_at=now + timedelta(days=7),
    )
    export_task = FlowchartTask(
        id=uuid4(),
        user_id="user-a",
        type=TaskType.DIAGRAM_EXPORT.value,
        status=TaskStatus.SUCCESS.value,
        request_snapshot={"diagramData": "snapshot"},
        document_id=document.id,
        idempotency_key=str(uuid4()),
        expires_at=now + timedelta(days=7),
    )
    event = FlowchartEvent(
        id=uuid4(),
        user_id="user-a",
        event_name="task_completed",
        task_id=source_task.id,
        document_id=document.id,
        payload={"diagramData": "snapshot"},
    )
    provider_call = FlowchartProviderCall(
        id=uuid4(),
        task_id=source_task.id,
        user_id="user-a",
        provider_id="provider-a",
        model_name="model-a",
        protocol="openai_chat",
        operation="submit",
        status="success",
    )
    file = FlowchartFile(
        id=uuid4(),
        user_id="user-a",
        document_id=document.id,
        task_id=export_task.id,
        original_name="审批流程.svg",
        stored_path="export/approval.svg",
        file_size=4,
        mime_type="image/svg+xml",
        format="SVG",
        file_role="export",
        expires_at=now + timedelta(hours=1),
    )
    session = _Session(
        document,
        [source_task, export_task],
        [event],
        [provider_call],
        [file],
    )
    storage = _Storage()
    storage.remove.return_value = True

    result = await document_service.delete_document(
        session,
        "user-a",
        document.id,
        storage=storage,
    )

    assert result.document_id == document.id
    assert session.deleted == [event, provider_call, file, source_task, export_task, document]
    storage.remove.assert_awaited_once_with("export/approval.svg")
    session.commit.assert_awaited_once()


def test_save_request_rejects_client_mermaid_source():
    with pytest.raises(ValidationError):
        DiagramSaveRequest.model_validate(
            {
                "version": 1,
                "title": "审批流程",
                "direction": "TB",
                "nodes": [],
                "edges": [],
                "mermaidSource": "flowchart TB",
            }
        )


def test_export_filename_removes_path_and_windows_reserved_names():
    assert document_service.sanitize_export_filename("../../审批流程", "mmd") == "审批流程.mmd"
    assert document_service.sanitize_export_filename("CON", "json") == "flowchart.json"
    assert document_service.sanitize_export_filename("CON.txt", "svg") == "flowchart.svg"
