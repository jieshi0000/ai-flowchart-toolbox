"""Provider 自动路由、手动选择与有限安全降级。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.providers.base import ProviderSubmission
from app.providers.provider_registry import ProviderRegistration, ProviderRegistry, ProviderSelectionError
from app.providers.transport import ProviderTransportError
from app.schemas.provider import ProviderCapability


@dataclass(frozen=True)
class ProviderRouteResult:
    """一次 Provider 提交的实际路由结果。"""

    registration: ProviderRegistration
    submission: ProviderSubmission
    attempts: tuple[str, ...]
    fallback_from: str | None = None
    fallback_reason: str | None = None

    @property
    def provider_id(self) -> str:
        return self.registration.provider_id

    @property
    def model(self) -> str:
        return self.registration.config.model


class ProviderRouter:
    """使用注册中心执行自动优先级路由和一次性安全降级。"""

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def candidates(
        self,
        required_capabilities: Iterable[ProviderCapability | str] | None = None,
        *,
        provider_id: str | None = None,
        model: str | None = None,
    ) -> list[ProviderRegistration]:
        if provider_id is not None:
            return [
                self.registry.select(
                    required_capabilities,
                    provider_id=provider_id,
                    model=model,
                )
            ]
        return self.registry.candidates(
            required_capabilities,
            model=model,
            # 模型选择来自用户时，只接受 allowManualSelection=true 的配置。
            manual=model is not None,
        )

    async def submit(
        self,
        request: Mapping[str, Any],
        required_capabilities: Iterable[ProviderCapability | str] | None = (
            ProviderCapability.TEXT_GENERATION,
        ),
        *,
        provider_id: str | None = None,
        model: str | None = None,
        **provider_kwargs: Any,
    ) -> ProviderRouteResult:
        candidates = self.candidates(
            required_capabilities,
            provider_id=provider_id,
            model=model,
        )
        if not candidates:
            raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "没有满足能力要求的可用供应商")

        # 自动降级最多尝试第二个候选；手动 providerId 的候选列表只有一个，
        # 因而不会私自切换到其他供应商。
        attempts: list[str] = []
        first_failure: ProviderTransportError | None = None
        for index, registration in enumerate(candidates[:2]):
            attempts.append(registration.provider_id)
            provider = self.registry.build_provider(registration.provider_id, **provider_kwargs)
            try:
                submission = await provider.submit(dict(request))
            except ProviderTransportError as exc:
                if index == 0 and len(candidates) > 1 and exc.fallback_allowed:
                    first_failure = exc
                    continue
                raise
            return ProviderRouteResult(
                registration=registration,
                submission=submission,
                attempts=tuple(attempts),
                fallback_from=attempts[0] if first_failure is not None else None,
                fallback_reason=first_failure.code if first_failure is not None else None,
            )

        # 只有候选供应商本身抛出错误才会走到这里；保留明确错误以免静默成功。
        if first_failure is not None:
            raise first_failure
        raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "没有满足能力要求的可用供应商")

    submit_with_fallback = submit


__all__ = ["ProviderRouteResult", "ProviderRouter"]
