"""流程图导出文件下载接口。"""

from __future__ import annotations

from urllib.parse import quote
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.flowchart_auth import current_flowchart_user_id
from app.core.database import get_session
from app.services.file_service import download_file


router = APIRouter(prefix="/flowchart/files", tags=["流程图文件"])


@router.get("/download", summary="下载流程图导出文件")
async def download_flowchart_file(
    request: Request,
    file_id: Annotated[UUID, Query(alias="fileId")],
    session: AsyncSession = Depends(get_session),
):
    file = await download_file(session, current_flowchart_user_id(request), file_id)
    return Response(
        content=file.content,
        media_type=file.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.filename, safe='')}",
            "Content-Length": str(len(file.content)),
            "Cache-Control": "private, no-store",
        },
    )


__all__ = ["router"]
