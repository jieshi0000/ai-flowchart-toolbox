"""Provider 公开信息服务。"""

from __future__ import annotations

from collections.abc import Iterable

from app.providers.provider_registry import ProviderRegistry, get_provider_registry
from app.schemas.provider import ProviderCapability, ProviderPublicInfo


def list_public_providers(
    required_capabilities: Iterable[ProviderCapability | str] | None = None,
    *,
    registry: ProviderRegistry | None = None,
) -> list[ProviderPublicInfo]:
    """返回可供前端展示的供应商信息，不包含任何私有配置。"""

    current = registry or get_provider_registry()
    return current.public_infos(required_capabilities)


__all__ = ["list_public_providers"]
