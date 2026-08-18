from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.template_service import list_system_templates


def _config(direction: str = "TB") -> dict:
    return {
        "title": "请假审批流程",
        "direction": direction,
        "nodes": [
            {"id": "start", "type": "start", "label": "开始"},
            {"id": "end", "type": "end", "label": "结束"},
        ],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
        "metadata": {"version": 1},
    }


class _Session:
    def __init__(self, templates):
        self.templates = templates
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.templates))


@pytest.mark.asyncio
async def test_list_system_templates_returns_only_workbench_summary_fields():
    template = SimpleNamespace(
        id=uuid4(),
        category="审批",
        name="请假审批",
        description="员工提交请假申请，主管审批。",
        config=_config("LR"),
    )
    session = _Session([template])

    result = await list_system_templates(session)

    assert result[0].id == template.id
    assert result[0].direction == "LR"
    assert result[0].description == "员工提交请假申请，主管审批。"
    statement = str(session.statements[0])
    assert "flowchart_template.enabled IS true" in statement
    assert "flowchart_template.user_id IS NULL" in statement


@pytest.mark.asyncio
async def test_list_system_templates_skips_invalid_persisted_config():
    template = SimpleNamespace(
        id=uuid4(),
        category="审批",
        name="损坏模板",
        description="",
        config={"direction": "TB"},
    )

    assert await list_system_templates(_Session([template])) == []
