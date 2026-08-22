"""流程图文档保存、读取与语义导出接口。"""

from __future__ import annotations

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.flowchart_auth import current_flowchart_user_id
from app.core.database import get_session
from app.schemas.common import Result
from app.schemas.diagram import DiagramSaveRequest
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentSaveResponse,
    FlowchartDocumentHistoryPage,
    FlowchartDocumentResponse,
)
from app.schemas.export import ExportRequest, ExportTaskResponse
from app.services.document_service import (
    DocumentVersionConflict,
    create_document_export,
    delete_document,
    get_document,
    list_documents,
    save_document,
)


router = APIRouter(prefix="/flowchart/documents", tags=["流程图文档"])


@router.get(
    "/get",
    response_model=Result[FlowchartDocumentResponse],
    summary="查询流程图文档",
)
async def get_flowchart_document(
    request: Request,
    document_id: Annotated[UUID, Query(alias="documentId")],
    session: AsyncSession = Depends(get_session),
):
    return Result.success(
        data=await get_document(session, current_flowchart_user_id(request), document_id)
    )


@router.get(
    "/list",
    response_model=Result[FlowchartDocumentHistoryPage],
    summary="查询最近流程图",
)
async def list_flowchart_documents(
    request: Request,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    session: AsyncSession = Depends(get_session),
):
    return Result.success(
        data=await list_documents(
            session,
            current_flowchart_user_id(request),
            offset=offset,
            limit=limit,
        )
    )


@router.post(
    "/save",
    response_model=Result[DocumentSaveResponse],
    summary="保存流程图文档",
)
async def save_flowchart_document(
    payload: DiagramSaveRequest,
    request: Request,
    document_id: Annotated[UUID, Query(alias="documentId")],
    session: AsyncSession = Depends(get_session),
):
    try:
        saved = await save_document(
            session,
            current_flowchart_user_id(request),
            document_id,
            payload,
            schedule_compilation=_enqueue_document_mermaid_compilation,
        )
    except DocumentVersionConflict as exc:
        latest = exc.document
        return Result(
            code=409,
            data=DocumentSaveResponse(
                document_id=UUID(latest.id or str(document_id)),
                version=latest.metadata.version,
                mermaid_source=latest.mermaid_source,
                mermaid_compilation=latest.mermaid_compilation,
                latest_document=latest,
            ),
            message="文档版本已更新，已返回最新内容",
            error_code="DOCUMENT_VERSION_CONFLICT",
        )
    return Result.success(data=saved)


@router.post(
    "/export",
    response_model=Result[ExportTaskResponse],
    summary="创建流程图语义导出",
)
async def export_flowchart_document(
    payload: ExportRequest,
    request: Request,
    document_id: Annotated[UUID, Query(alias="documentId")],
    session: AsyncSession = Depends(get_session),
):
    return Result.success(
        data=await create_document_export(
            session,
            current_flowchart_user_id(request),
            document_id,
            payload,
            schedule_render=_enqueue_document_export,
        )
    )


@router.post(
    "/delete",
    response_model=Result[DocumentDeleteResponse],
    summary="永久删除流程图",
)
async def delete_flowchart_document(
    request: Request,
    document_id: Annotated[UUID, Query(alias="documentId")],
    session: AsyncSession = Depends(get_session),
):
    return Result.success(
        data=await delete_document(
            session,
            current_flowchart_user_id(request),
            document_id,
        )
    )


def _enqueue_document_mermaid_compilation(document_id: UUID, version: int) -> None:
    from app.workers.tasks import enqueue_document_mermaid_compilation

    asyncio.get_running_loop().run_in_executor(
        None,
        enqueue_document_mermaid_compilation,
        document_id,
        version,
    )


def _enqueue_document_export(task_id: UUID) -> None:
    from app.workers.tasks import enqueue_document_export

    asyncio.get_running_loop().run_in_executor(
        None,
        enqueue_document_export,
        task_id,
    )


__all__ = ["router"]
