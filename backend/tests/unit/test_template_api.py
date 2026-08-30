from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.template import FlowchartTemplateSummary


@pytest.mark.asyncio
async def test_template_list_api_returns_summary_without_template_config(monkeypatch):
    from app.api import template_api

    item = FlowchartTemplateSummary(
        id=uuid4(),
        category="审批",
        name="请假审批",
        description="员工提交请假申请，主管审批。",
        direction="TB",
    )

    async def fake_list_system_templates(session):
        assert isinstance(session, SimpleNamespace)
        return [item]

    monkeypatch.setattr(template_api, "list_system_templates", fake_list_system_templates)
    result = await template_api.get_template_list(SimpleNamespace())
    dumped = result.model_dump(by_alias=True)

    assert dumped["data"][0]["name"] == "请假审批"
    assert dumped["data"][0]["direction"] == "TB"
    assert "config" not in dumped["data"][0]
