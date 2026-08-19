"""广场身份、额度和用量上报的本地端口。

首期只保留可替换接口；本地实现不发起任何广场网络请求，导出任务成本固定为
零，后续接入广场时可以在边界层替换实现而不改动任务状态机。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class IdentityProvider(Protocol):
    async def current_identity(self, request_context: Mapping[str, object]) -> str | None: ...


class QuotaPort(Protocol):
    async def reserve(self, user_id: str, points: int) -> bool: ...

    async def settle(self, user_id: str, points: int, *, success: bool) -> None: ...


class UsageReporter(Protocol):
    async def report(self, user_id: str, usage: Mapping[str, object]) -> None: ...


class LocalIdentityProvider:
    async def current_identity(self, request_context: Mapping[str, object]) -> str | None:
        value = request_context.get("user_id")
        return str(value) if value else None


class UnlimitedQuotaPort:
    async def reserve(self, user_id: str, points: int) -> bool:
        return True

    async def settle(self, user_id: str, points: int, *, success: bool) -> None:
        return None


class NoopUsageReporter:
    async def report(self, user_id: str, usage: Mapping[str, object]) -> None:
        return None


__all__ = [
    "IdentityProvider",
    "LocalIdentityProvider",
    "NoopUsageReporter",
    "QuotaPort",
    "UnlimitedQuotaPort",
    "UsageReporter",
]
