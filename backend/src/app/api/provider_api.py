from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.schemas.common import Result
from app.schemas.provider import ProviderCapability, ProviderPublicInfo
from app.services.provider_service import list_public_providers


router = APIRouter(prefix="/flowchart/providers", tags=["流程图供应商"])


def _capability_values(
    capability: list[ProviderCapability] | None,
    capabilities: list[str] | str | None,
) -> list[ProviderCapability] | None:
    values = list(capability or [])
    raw_values = [capabilities] if isinstance(capabilities, str) else (capabilities or [])
    for raw_value in raw_values:
        for item in raw_value.split(","):
            item = item.strip()
            if item:
                values.append(ProviderCapability(item))
    return values or None


@router.get(
    "/list",
    response_model=Result[list[ProviderPublicInfo]],
    summary="获取供应商公开列表",
)
async def get_provider_list(
    capability: Annotated[list[ProviderCapability] | None, Query()] = None,
    capabilities: Annotated[list[str] | None, Query(description="能力筛选，可重复或逗号分隔")] = None,
):
    return Result.success(
        data=list_public_providers(_capability_values(capability, capabilities))
    )


@router.get(
    "",
    response_model=Result[list[ProviderPublicInfo]],
    include_in_schema=False,
)
async def get_provider_list_legacy(
    capability: Annotated[list[ProviderCapability] | None, Query()] = None,
    capabilities: Annotated[list[str] | None, Query(description="能力筛选，可重复或逗号分隔")] = None,
):
    """兼容设计文档早期的无 /list 路径。"""

    return Result.success(
        data=list_public_providers(_capability_values(capability, capabilities))
    )


__all__ = ["router"]
