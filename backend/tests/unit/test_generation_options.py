from types import SimpleNamespace

from app.providers.generation_prompt import build_generation_prompt
from app.schemas.task import TaskCreateRequest
from app.services.task_engine import _apply_task_theme


def test_task_request_accepts_diagram_theme_alias_and_keeps_options_in_snapshot_shape():
    request = TaskCreateRequest(
        prompt="员工提交申请并等待审批",
        detailLevel="detailed",
        diagramTheme="purple",
        idempotencyKey="generation-1",
    )

    assert request.detail_level.value == "detailed"
    assert request.diagram_theme.value == "purple"
    snapshot = request.model_dump(mode="json", exclude={"idempotency_key"})
    assert snapshot["detail_level"] == "detailed"
    assert snapshot["diagram_theme"] == "purple"


def test_task_request_defaults_to_disabled_thinking_and_accepts_deep_thinking_alias():
    assert TaskCreateRequest(prompt="生成流程", idempotencyKey="generation-2").thinking_enabled is False
    canonical = TaskCreateRequest(
        prompt="生成流程",
        thinkingEnabled=True,
        idempotencyKey="generation-2-canonical",
    )
    assert canonical.thinking_enabled is True
    enabled = TaskCreateRequest(
        prompt="生成流程",
        deepThinking=True,
        idempotencyKey="generation-3",
    )
    assert enabled.thinking_enabled is True
    assert enabled.model_dump(mode="json")["thinking_enabled"] is True


def test_generation_prompt_contains_direction_detail_and_theme_constraints():
    prompt = build_generation_prompt(
        {
            "prompt": "员工提交申请并等待审批",
            "direction": "LR",
            "detail_level": "concise",
            "diagram_theme": "green",
        }
    )

    assert "流程图方向必须是 LR" in prompt
    assert "简要" in prompt
    assert "清新绿" in prompt
    assert "style" in prompt


def test_task_theme_overrides_model_node_styles_and_records_theme():
    task = SimpleNamespace(
        request_snapshot={"diagram_theme": "purple"},
    )
    payload = {
        "title": "审批流程",
        "direction": "TB",
        "nodes": [
            {
                "id": "n1",
                "type": "process",
                "label": "提交",
                "style": {"fill": "#FFFFFF", "stroke": "#000000"},
            }
        ],
        "edges": [],
    }

    themed = _apply_task_theme(payload, task)

    assert themed["nodes"][0]["style"] == {"fill": "#F5F1FF", "stroke": "#D3C7FF"}
    assert themed["metadata"]["theme"] == "purple"
