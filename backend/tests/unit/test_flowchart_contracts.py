import math
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.providers.base import ModelProvider, ProviderPollResult, ProviderResult, ProviderSubmission
from app.models.document import FlowchartDocument
from app.models.event import FlowchartEvent
from app.models.file import FlowchartFile
from app.models.provider_call import FlowchartProviderCall
from app.models.quota import FlowchartQuotaLog
from app.models.task import FlowchartTask
from app.models.template import FlowchartTemplate
from app.schemas.diagram import DiagramDocument, DiagramGenerationResult, DiagramSaveRequest
from app.schemas.export import ExportFormat, ExportRequest
from app.schemas.provider import ProviderConfig
from app.schemas.task import TaskCreateRequest, TaskStatus


def _node(node_id="start", node_type="start", label="开始"):
    return {"id": node_id, "type": node_type, "label": label, "position": {"x": 0, "y": 0}}


def _doc(**kwargs):
    value = {
        "title": "示例流程",
        "direction": "TB",
        "nodes": [_node(), _node("end", "end", "结束")],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }
    value.update(kwargs)
    return value


class TestDiagramContract:
    def test_all_node_types_and_cycle_are_valid(self):
        types = ["start", "end", "process", "decision", "input_output", "subprocess"]
        nodes = [_node(t, t, t) for t in types]
        edges = [{"id": f"e{i}", "source": types[i], "target": types[(i + 1) % len(types)]} for i in range(len(types))]
        document = DiagramDocument(**_doc(nodes=nodes, edges=edges))
        assert document.direction == "TB"
        assert len(document.nodes) == 6

    @pytest.mark.parametrize("field,value", [("title", "x" * 101), ("nodes", [_node(str(i)) for i in range(51)])])
    def test_limits_are_enforced(self, field, value):
        with pytest.raises(ValidationError):
            DiagramDocument(**_doc(**{field: value}))

    def test_edge_limit_and_label_limit(self):
        nodes = [_node("a"), _node("b", "end", "结束")]
        edges = [{"id": f"e{i}", "source": "a", "target": "b"} for i in range(101)]
        with pytest.raises(ValidationError):
            DiagramDocument(**_doc(nodes=nodes, edges=edges))
        with pytest.raises(ValidationError):
            DiagramDocument(**_doc(nodes=[_node("a", "start", "x" * 121), _node("b", "end", "结束")]))

    @pytest.mark.parametrize("payload", [
        _doc(nodes=[_node("same"), _node("same", "end", "结束")]),
        _doc(edges=[{"id": "e1", "source": "missing", "target": "end"}]),
        _doc(nodes=[_node("a", "not_a_type", "a")]),
        _doc(title="<script>alert(1)</script>"),
    ])
    def test_invalid_graph_is_rejected(self, payload):
        with pytest.raises(ValidationError):
            DiagramDocument(**payload)

    def test_coordinates_must_be_finite_and_mermaid_is_derived_field(self):
        with pytest.raises(ValidationError):
            DiagramDocument(**_doc(nodes=[_node("a"), {**_node("b", "end", "结束"), "position": {"x": math.inf, "y": 0}}]))
        assert DiagramDocument(**_doc()).mermaid_source == ""
        with pytest.raises(ValidationError):
            DiagramGenerationResult(**_doc(mermaidSource="client text"))
        with pytest.raises(ValidationError):
            DiagramSaveRequest(**_doc(version=1, mermaidSource="client text"))


class TestTaskProviderExportContracts:
    def test_task_request_aliases_and_bounds(self):
        request = TaskCreateRequest(
            prompt="  生成流程  ",
            sessionId=" browser-session-1 ",
            idempotencyKey="idem-1",
        )
        assert request.prompt == "生成流程"
        assert request.session_id == "browser-session-1"
        assert request.detail_level.value == "standard"
        with pytest.raises(ValidationError):
            TaskCreateRequest(prompt="x" * 4001, idempotencyKey="k")
        with pytest.raises(ValidationError):
            TaskCreateRequest(prompt="流程", sessionId="contains spaces", idempotencyKey="k")

    def test_provider_public_config_requires_same_display_name_and_model(self):
        config = ProviderConfig(
            providerId="provider-1", displayName="model-a", model="model-a",
            adapter="openai_compatible", protocol="openai_chat_completions",
            baseUrl="https://provider.invalid", apiKeyEnv="PROVIDER_KEY",
            capabilities=["text_generation"],
        )
        assert config.display_name == config.model
        public = config.model_dump(include={"provider_id", "display_name", "model", "capabilities"})
        assert "api_key_env" not in public
        with pytest.raises(ValidationError):
            ProviderConfig(
                providerId="provider-1", displayName="different", model="model-a",
                adapter="openai_compatible", protocol="openai_chat_completions",
                baseUrl="https://provider.invalid", apiKeyEnv="PROVIDER_KEY",
                capabilities=["text_generation"],
            )

    def test_export_formats_are_closed(self):
        assert {item.value for item in ExportFormat} == {"SVG", "PNG", "MERMAID", "JSON"}
        assert ExportRequest(format="SVG").background.value == "transparent"
        with pytest.raises(ValidationError):
            ExportRequest(format="PDF")

    def test_provider_protocol_results_validate(self):
        submission = ProviderSubmission(mode="sync", status="succeeded", result={"title": "x"})
        assert submission.mode == "sync"
        assert ProviderPollResult(status="processing", progress=50).progress == 50
        assert ProviderResult(success=True, provider="p", model="m", data={}).success is True
        with pytest.raises(ValueError):
            ProviderPollResult(status="processing", progress=101)
        with pytest.raises(ValueError):
            ProviderResult(success=True, provider="p", model="m")

    def test_task_status_has_expected_terminal_values(self):
        assert {TaskStatus.SUCCESS.value, TaskStatus.FAILED.value, TaskStatus.CANCELED.value, TaskStatus.EXPIRED.value} <= {item.value for item in TaskStatus}


def test_provider_interface_is_abstract():
    assert ModelProvider.__abstractmethods__ == {"submit", "poll", "cancel", "health_check"}


def test_flowchart_orm_columns_match_append_only_table_contract():
    assert "updated_at" in FlowchartDocument.__table__.columns
    assert "updated_at" in FlowchartTask.__table__.columns
    assert "session_id" in FlowchartTask.__table__.columns
    assert "updated_at" in FlowchartTemplate.__table__.columns
    for model in (FlowchartFile, FlowchartQuotaLog, FlowchartProviderCall, FlowchartEvent):
        assert "created_at" in model.__table__.columns
        assert "updated_at" not in model.__table__.columns
