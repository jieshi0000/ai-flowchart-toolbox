import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.document import FlowchartDocument
from app.models.file import FlowchartFile
from app.models.task import FlowchartTask
from app.schemas.export import ExportBackground, ExportFormat, ExportRequest
from app.schemas.task import TaskStatus, TaskType
from app.services import document_service, export_renderer, export_service, file_service
from app.services.plaza import (
    LocalIdentityProvider,
    NoopUsageReporter,
    UnlimitedQuotaPort,
)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value if isinstance(self.value, list) else [self.value]


class _Session:
    def __init__(self, *values):
        self.values = list(values)
        self.added = []
        self.deleted = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, _statement):
        value = self.values.pop(0) if self.values else None
        return _ScalarResult(value)

    def add(self, value):
        self.added.append(value)

    async def delete(self, value):
        self.deleted.append(value)


def _factory(session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


def _document():
    now = datetime.now(UTC).replace(tzinfo=None)
    return FlowchartDocument(
        id=uuid4(),
        user_id="user-a",
        title="中文审批流程",
        direction="TB",
        diagram_data={
            "title": "中文审批流程",
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
            "metadata": {"version": 3},
        },
        mermaid_source="flowchart TB",
        version=3,
        expires_at=now + timedelta(days=30),
    )


def test_build_diagram_svg_is_script_free_and_keeps_chinese_text():
    svg = export_renderer.build_diagram_svg(_document().diagram_data)

    assert svg.startswith("<svg")
    assert "开始" in svg
    assert "Source Han Sans SC" in svg
    assert "<script" not in svg.lower()
    assert 'marker-end="url(#flowchart-arrow)"' in svg


def test_rendered_content_rejects_active_or_external_svg_content():
    assert export_renderer.is_valid_rendered_content(
        ExportFormat.SVG,
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    ) is False
    assert export_renderer.is_valid_rendered_content(
        ExportFormat.SVG,
        b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.com/a.svg"/></svg>',
    ) is False
    assert export_renderer.is_valid_rendered_content(
        ExportFormat.SVG,
        b'<svg xmlns="http://www.w3.org/2000/svg"><title>ok</title></svg>',
    ) is True
    assert export_renderer.is_valid_rendered_content(
        ExportFormat.SVG,
        b'<svg xmlns="http://www.w3.org/2000/svg"><rect style="fill:url(https://example.com/a)"/></svg>',
    ) is False
    assert export_renderer.is_valid_rendered_content(
        ExportFormat.SVG,
        b'<svg xmlns="http://www.w3.org/2000/svg"><animate attributeName="x"/></svg>',
    ) is False
    assert export_renderer.is_valid_rendered_content(
        ExportFormat.SVG,
        b'<svg xmlns="http://www.w3.org/2000/svg"><use href="#node"/></svg>',
    ) is False
    assert export_renderer.is_valid_rendered_content(
        ExportFormat.SVG,
        b'<?xml-stylesheet href="https://example.com/a.css"?><svg xmlns="http://www.w3.org/2000/svg"/>',
    ) is False


def test_rendered_content_checks_png_signature():
    assert export_renderer.is_valid_rendered_content(
        ExportFormat.PNG,
        b"\x89PNG\r\n\x1a\nminimal",
    ) is True
    assert export_renderer.is_valid_rendered_content(ExportFormat.PNG, b"PNG") is False


@pytest.mark.asyncio
async def test_local_plaza_ports_do_not_make_network_calls():
    assert await LocalIdentityProvider().current_identity({"user_id": "user-a"}) == "user-a"
    quota = UnlimitedQuotaPort()
    assert await quota.reserve("user-a", 0) is True
    assert await quota.settle("user-a", 0, success=True) is None
    assert await NoopUsageReporter().report("user-a", {"costPoints": 0}) is None


@pytest.mark.asyncio
async def test_renderer_timeout_is_mapped_to_export_render_failed(monkeypatch):
    async def hang(*_args, **_kwargs):
        await asyncio.sleep(2)

    monkeypatch.setattr(export_renderer.ChromiumExportRenderer, "_render_with_browser", hang)
    monkeypatch.setattr(
        export_renderer,
        "get_settings",
        lambda: SimpleNamespace(
            export=SimpleNamespace(render_timeout_ms=1_000, temp_dir="", max_file_size=100_000)
        ),
    )

    with pytest.raises(export_renderer.ExportRenderError) as exc_info:
        await export_renderer.ChromiumExportRenderer().render(
            {"diagramData": _document().diagram_data},
            ExportFormat.SVG,
            ExportBackground.TRANSPARENT,
        )

    assert exc_info.value.error_code == "EXPORT_RENDER_FAILED"


@pytest.mark.asyncio
async def test_renderer_timeout_closes_all_browser_resources(monkeypatch, tmp_path):
    calls: list[str] = []

    class _Page:
        async def goto(self, *_args, **_kwargs):
            await asyncio.sleep(2)

        async def close(self):
            calls.append("page")

    class _Context:
        async def new_page(self):
            return _Page()

        async def close(self):
            calls.append("context")

    class _Browser:
        async def new_context(self, *_args, **_kwargs):
            return _Context()

        async def close(self):
            calls.append("browser")

    class _Playwright:
        chromium = None

        def __init__(self):
            self.chromium = self

        async def launch(self, *_args, **_kwargs):
            return _Browser()

        async def stop(self):
            calls.append("playwright")

    class _Starter:
        async def start(self):
            return _Playwright()

    module = ModuleType("playwright.async_api")
    module.async_playwright = lambda: _Starter()
    monkeypatch.setitem(sys.modules, "playwright.async_api", module)
    monkeypatch.setattr(
        export_renderer,
        "get_settings",
        lambda: SimpleNamespace(
            export=SimpleNamespace(
                render_timeout_ms=1_000,
                temp_dir=str(tmp_path),
                max_file_size=100_000,
                chromium_path="",
            )
        ),
    )

    with pytest.raises(export_renderer.ExportRenderError) as exc_info:
        await export_renderer.ChromiumExportRenderer().render(
            {"diagramData": _document().diagram_data},
            ExportFormat.SVG,
            ExportBackground.TRANSPARENT,
        )

    assert exc_info.value.error_code == "EXPORT_RENDER_FAILED"
    assert set(calls) == {"page", "context", "browser", "playwright"}
    assert not list(tmp_path.glob("flowchart-export-*"))


@pytest.mark.asyncio
async def test_svg_export_creates_waiting_task_and_freezes_document_snapshot():
    document = _document()
    session = _Session(document)
    scheduler = Mock()

    result = await document_service.create_document_export(
        session,
        "user-a",
        document.id,
        ExportRequest(format=ExportFormat.SVG, background=ExportBackground.WHITE),
        schedule_render=scheduler,
    )

    assert result.status is TaskStatus.WAITING
    task = next(item for item in session.added if isinstance(item, FlowchartTask))
    assert task.status == TaskStatus.WAITING.value
    assert task.request_snapshot["version"] == 3
    assert task.request_snapshot["background"] == "white"
    assert task.request_snapshot["diagramData"]["title"] == "中文审批流程"
    assert str(scheduler.call_args.args[0]) == str(task.id)


class _Storage:
    def __init__(self):
        self.put_bytes = AsyncMock()
        self.remove = AsyncMock()
        self.get_bytes = AsyncMock(return_value=b"file")


class _Renderer:
    async def render(self, _snapshot, _format, _background):
        return b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'


@pytest.mark.asyncio
async def test_export_worker_does_not_duplicate_a_fresh_rendering_task():
    task = FlowchartTask(
        id=uuid4(),
        user_id="user-a",
        type=TaskType.DIAGRAM_EXPORT.value,
        status=TaskStatus.RENDERING.value,
        request_snapshot={},
        idempotency_key=str(uuid4()),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
    session = _Session(task)
    renderer = Mock()
    renderer.render = AsyncMock()

    await export_service.render_document_export(
        task.id,
        session_factory=_factory(session),
        storage=_Storage(),
        renderer=renderer,
    )

    renderer.render.assert_not_awaited()


@pytest.mark.asyncio
async def test_export_worker_uploads_file_and_exposes_download_url(monkeypatch):
    task = FlowchartTask(
        id=uuid4(),
        user_id="user-a",
        type=TaskType.DIAGRAM_EXPORT.value,
        status=TaskStatus.WAITING.value,
        progress=5,
        stage="等待导出渲染",
        request_snapshot={
            "documentId": str(uuid4()),
            "version": 3,
            "title": "中文审批流程",
            "diagramData": _document().diagram_data,
            "format": "SVG",
            "background": "transparent",
        },
        result={},
        idempotency_key=str(uuid4()),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    session = _Session(task, task)
    storage = _Storage()
    monkeypatch.setattr(export_service, "_publish", AsyncMock())
    monkeypatch.setattr(
        export_service,
        "get_settings",
        lambda: SimpleNamespace(export=SimpleNamespace(max_file_size=100_000)),
    )

    await export_service.render_document_export(
        task.id,
        session_factory=_factory(session),
        storage=storage,
        renderer=_Renderer(),
    )

    assert task.status == TaskStatus.SUCCESS.value
    assert task.output_file_id is not None
    assert task.result["downloadUrl"].endswith(str(task.output_file_id))
    file = next(item for item in session.added if isinstance(item, FlowchartFile))
    assert file.format == "SVG"
    assert file.mime_type == "image/svg+xml"
    storage.put_bytes.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_expired_export_file_removes_object_and_record():
    expired = FlowchartFile(
        id=uuid4(),
        user_id="user-a",
        original_name="过期.svg",
        stored_path="export/expired.svg",
        file_size=4,
        mime_type="image/svg+xml",
        format="SVG",
        file_role="export",
        expires_at=datetime(2024, 1, 1),
    )
    session = _Session([expired])
    storage = _Storage()

    removed = await file_service.cleanup_expired_files(
        session,
        storage=storage,
        now=datetime(2024, 1, 2, tzinfo=UTC),
    )

    assert removed == 1
    assert session.deleted == [expired]
    storage.remove.assert_awaited_once_with("export/expired.svg")


@pytest.mark.asyncio
async def test_cleanup_keeps_record_when_object_delete_is_deferred():
    expired = FlowchartFile(
        id=uuid4(),
        user_id="user-a",
        original_name="过期.svg",
        stored_path="export/expired.svg",
        file_size=4,
        mime_type="image/svg+xml",
        format="SVG",
        file_role="export",
        expires_at=datetime(2024, 1, 1),
    )
    session = _Session([expired])
    storage = _Storage()
    storage.remove.return_value = False

    removed = await file_service.cleanup_expired_files(
        session,
        storage=storage,
        now=datetime(2024, 1, 2, tzinfo=UTC),
    )

    assert removed == 0
    assert session.deleted == []
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_file_checks_owner_and_expiry():
    file = FlowchartFile(
        id=uuid4(),
        user_id="user-a",
        original_name="流程图.svg",
        stored_path="export/a.svg",
        file_size=4,
        mime_type="image/svg+xml",
        format="SVG",
        file_role="export",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )
    session = _Session(file)
    storage = _Storage()

    with pytest.raises(Exception) as exc_info:
        await file_service.download_file(session, "user-b", file.id, storage=storage)
    assert getattr(exc_info.value, "code", None) == 403

    expired = FlowchartFile(
        id=uuid4(),
        user_id="user-a",
        original_name="过期.svg",
        stored_path="export/expired.svg",
        file_size=0,
        mime_type="image/svg+xml",
        format="SVG",
        file_role="export",
        expires_at=datetime(2020, 1, 1),
    )
    expired_session = _Session(expired)
    with pytest.raises(Exception) as exc_info:
        await file_service.download_file(
            expired_session,
            "user-a",
            expired.id,
            storage=storage,
            now=datetime(2024, 1, 1, tzinfo=UTC),
        )
    assert getattr(exc_info.value, "error_code", None) == "EXPORT_FILE_EXPIRED"
    storage.remove.assert_awaited()
