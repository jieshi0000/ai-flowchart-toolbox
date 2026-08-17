"""流程图本地任务接口。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.exceptions.business import BusinessException
from app.schemas.common import Result
from app.schemas.task import (
    TaskCancelResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskRetryResponse,
    TaskStatusResponse,
)
from app.services.task_service import (
    cancel_task,
    create_task,
    get_task,
    retry_task,
)


router = APIRouter(prefix="/flowchart/tasks", tags=["流程图任务"])


def _current_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if isinstance(user_id, str) and user_id.strip():
        return user_id

    # 测试和无认证的纯本地模式没有会话中间件身份；该头在认证开启时完全不参与鉴权。
    if not get_settings().auth.enabled:
        local_user_id = request.headers.get("X-Flowchart-User-Id", "local-user").strip()
        if local_user_id and len(local_user_id) <= 64:
            return local_user_id

    raise BusinessException(code=401, message="未登录")


@router.post(
    "/create",
    response_model=Result[TaskCreateResponse],
    summary="创建流程图生成任务",
)
async def create_flowchart_task(
    payload: TaskCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    return Result.success(data=await create_task(session, _current_user_id(request), payload))


@router.get(
    "/get",
    response_model=Result[TaskStatusResponse],
    summary="查询流程图任务",
)
async def get_flowchart_task(
    request: Request,
    task_id: Annotated[UUID, Query(alias="taskId")],
    session: AsyncSession = Depends(get_session),
):
    return Result.success(data=await get_task(session, _current_user_id(request), task_id))


@router.post(
    "/cancel",
    response_model=Result[TaskCancelResponse],
    summary="取消流程图任务",
)
async def cancel_flowchart_task(
    request: Request,
    task_id: Annotated[UUID, Query(alias="taskId")],
    session: AsyncSession = Depends(get_session),
):
    return Result.success(data=await cancel_task(session, _current_user_id(request), task_id))


@router.post(
    "/retry",
    response_model=Result[TaskRetryResponse],
    summary="重试流程图任务",
)
async def retry_flowchart_task(
    request: Request,
    task_id: Annotated[UUID, Query(alias="taskId")],
    session: AsyncSession = Depends(get_session),
):
    return Result.success(data=await retry_task(session, _current_user_id(request), task_id))


__all__ = ["router"]
