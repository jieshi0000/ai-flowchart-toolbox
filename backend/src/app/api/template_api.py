"""流程图系统模板接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.common import Result
from app.schemas.template import FlowchartTemplateSummary
from app.services.template_service import list_system_templates


router = APIRouter(prefix="/flowchart/templates", tags=["流程图模板"])


@router.get(
    "/list",
    response_model=Result[list[FlowchartTemplateSummary]],
    summary="获取系统内置流程图模板",
)
async def get_template_list(session: AsyncSession = Depends(get_session)):
    return Result.success(data=await list_system_templates(session))


__all__ = ["router"]
