from uuid import UUID

from app.schemas.base import CamelVO
from app.schemas.diagram import DiagramDirection


class FlowchartTemplateSummary(CamelVO):
    """工作台模板列表的公开视图。"""

    id: UUID
    category: str
    name: str
    description: str
    direction: DiagramDirection
