"""流程图系统内置模板查询服务。"""

from __future__ import annotations

from loguru import logger
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import FlowchartTemplate
from app.schemas.diagram import DiagramTemplateConfig
from app.schemas.task import TaskType
from app.schemas.template import FlowchartTemplateSummary


def _to_summary(template: FlowchartTemplate) -> FlowchartTemplateSummary | None:
    try:
        config = DiagramTemplateConfig.model_validate(template.config)
    except ValidationError:
        # 单条维护异常不应让工作台无法输入描述；不记录模板正文，避免日志扩大数据面。
        logger.warning("skip invalid flowchart template templateId={}", template.id)
        return None

    return FlowchartTemplateSummary(
        id=template.id,
        category=template.category,
        name=template.name,
        description=template.description or "",
        direction=config.direction,
    )


async def list_system_templates(session: AsyncSession) -> list[FlowchartTemplateSummary]:
    """按后台配置顺序读取已启用的系统生成模板。"""

    result = await session.execute(
        select(FlowchartTemplate)
        .where(
            FlowchartTemplate.user_id.is_(None),
            FlowchartTemplate.type == TaskType.DIAGRAM_GENERATE.value,
            FlowchartTemplate.enabled.is_(True),
        )
        .order_by(FlowchartTemplate.sort_order.asc(), FlowchartTemplate.name.asc())
    )
    return [summary for template in result.scalars().all() if (summary := _to_summary(template)) is not None]


__all__ = ["list_system_templates"]
