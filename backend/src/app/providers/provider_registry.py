"""供应商配置注册中心与能力路由。

注册中心只保存服务端配置和适配器实例。任何公开信息都通过
``ProviderConfig.to_public_info`` 生成，避免误把 ``base_url`` 或密钥环境变量
返回给前端。
"""

from __future__ import annotations

import os
import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.config import Settings, get_settings
from app.providers.base import ModelProvider
from app.providers.config import load_provider_configs
from app.schemas.provider import (
    ProviderCapability,
    ProviderConfig,
    ProviderHealth,
    ProviderPublicInfo,
    ProviderStatus,
)


class ProviderSelectionError(RuntimeError):
    """没有可用于当前请求的供应商。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ProviderRegistration:
    config: ProviderConfig
    provider: ModelProvider | None
    health: ProviderHealth

    @property
    def provider_id(self) -> str:
        return self.config.provider_id

    @property
    def available(self) -> bool:
        return self.config.enabled and self.health.status is ProviderStatus.HEALTHY


def _normalise_capabilities(
    capabilities: Iterable[ProviderCapability | str] | None,
) -> frozenset[ProviderCapability]:
    if capabilities is None:
        return frozenset()
    result: set[ProviderCapability] = set()
    for capability in capabilities:
        result.add(capability if isinstance(capability, ProviderCapability) else ProviderCapability(capability))
    return frozenset(result)


class ProviderRegistry:
    """按配置顺序注册 Provider，并提供安全的自动/手动选择。"""

    def __init__(
        self,
        configs: Sequence[ProviderConfig] = (),
        *,
        providers: Mapping[str, ModelProvider] | None = None,
        key_lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        self._key_lookup = key_lookup or os.getenv
        self._registrations: dict[str, ProviderRegistration] = {}
        self._order: list[str] = []
        self._adapter_factories: dict[str, Callable[..., ModelProvider]] = {}
        provider_map = dict(providers or {})
        for config in configs:
            self.register(config, provider=provider_map.get(config.provider_id))

    @classmethod
    def from_file(
        cls,
        path: str | None = None,
        *,
        settings: Settings | None = None,
        providers: Mapping[str, ModelProvider] | None = None,
        key_lookup: Callable[[str], str | None] | None = None,
        allow_missing: bool = True,
    ) -> "ProviderRegistry":
        return cls(
            load_provider_configs(path, settings=settings, allow_missing=allow_missing),
            providers=providers,
            key_lookup=key_lookup,
        )

    def register(
        self,
        config: ProviderConfig,
        *,
        provider: ModelProvider | None = None,
        replace: bool = False,
    ) -> ProviderRegistration:
        if config.provider_id in self._registrations and not replace:
            raise ValueError("Provider providerId 不能重复")
        health = self._initial_health(config)
        registration = ProviderRegistration(config=config, provider=provider, health=health)
        if config.provider_id not in self._registrations:
            self._order.append(config.provider_id)
        self._registrations[config.provider_id] = registration
        return registration

    def register_provider(self, provider_id: str, provider: ModelProvider) -> ProviderRegistration:
        """为已注册配置绑定适配器实例。"""

        registration = self.get_registration(provider_id)
        updated = ProviderRegistration(registration.config, provider, registration.health)
        self._registrations[provider_id] = updated
        return updated

    def register_adapter(self, adapter: str, factory: Callable[..., ModelProvider]) -> None:
        """注册适配器工厂，供后续 D05/D06 适配器复用。"""

        normalized = str(adapter).strip()
        if not normalized:
            raise ValueError("adapter 不能为空")
        self._adapter_factories[normalized] = factory

    def build_provider(self, provider_id: str, **kwargs: Any) -> ModelProvider:
        registration = self.get_registration(provider_id)
        if registration.provider is not None:
            return registration.provider
        factory = self._adapter_factories.get(registration.config.adapter.value)
        if factory is None:
            raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "当前供应商适配器尚未注册")
        provider = factory(registration.config, **kwargs)
        self.register_provider(provider_id, provider)
        return provider

    @property
    def configs(self) -> tuple[ProviderConfig, ...]:
        return tuple(self._registrations[provider_id].config for provider_id in self._order)

    @property
    def registrations(self) -> tuple[ProviderRegistration, ...]:
        return tuple(self._registrations[provider_id] for provider_id in self._order)

    def get_registration(self, provider_id: str) -> ProviderRegistration:
        try:
            return self._registrations[provider_id]
        except KeyError as exc:
            raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "指定的供应商未配置") from exc

    def get_config(self, provider_id: str) -> ProviderConfig:
        return self.get_registration(provider_id).config

    def get_provider(self, provider_id: str) -> ModelProvider | None:
        return self.get_registration(provider_id).provider

    def has_api_key(self, config: ProviderConfig | str) -> bool:
        current = self.get_config(config) if isinstance(config, str) else config
        value = self._key_lookup(current.api_key_env)
        return bool(value and value.strip())

    def set_health(
        self,
        provider_id: str,
        status: ProviderStatus,
        *,
        latency_ms: int | None = None,
    ) -> ProviderRegistration:
        registration = self.get_registration(provider_id)
        health = ProviderHealth(status=status, latency_ms=latency_ms)
        updated = ProviderRegistration(registration.config, registration.provider, health)
        self._registrations[provider_id] = updated
        return updated

    async def refresh_health(self, provider_id: str | None = None) -> tuple[ProviderRegistration, ...]:
        """调用已绑定适配器的健康检查并更新缓存状态。

        没有适配器实例时不发起任何网络请求；检查异常只收敛为
        ``unhealthy``，不把供应商原始错误传播到公开接口。
        """

        targets = [self.get_registration(provider_id)] if provider_id else list(self.registrations)
        for registration in targets:
            provider = registration.provider
            if provider is None or not registration.config.enabled:
                continue
            try:
                result = provider.health_check()
                health = await result if inspect.isawaitable(result) else result
                if not isinstance(health, ProviderHealth):
                    raise TypeError("health_check 必须返回 ProviderHealth")
                self.set_health(
                    registration.provider_id,
                    health.status,
                    latency_ms=health.latency_ms,
                )
            except Exception:
                self.set_health(registration.provider_id, ProviderStatus.UNHEALTHY)
        return self.registrations

    health_check = refresh_health
    healthCheck = refresh_health

    def public_infos(
        self,
        required_capabilities: Iterable[ProviderCapability | str] | None = None,
        *,
        include_unavailable: bool = True,
    ) -> list[ProviderPublicInfo]:
        required = _normalise_capabilities(required_capabilities)
        result: list[ProviderPublicInfo] = []
        for registration in self.registrations:
            config = registration.config
            if not config.enabled or not required.issubset(set(config.capabilities)):
                continue
            health = self._effective_health(registration)
            if not include_unavailable and health.status is not ProviderStatus.HEALTHY:
                continue
            result.append(config.to_public_info(status=health.status))
        return result

    # 常用别名，兼容调用方把公开列表称作 list_public。
    list_public = public_infos

    def candidates(
        self,
        required_capabilities: Iterable[ProviderCapability | str] | None = None,
        *,
        provider_id: str | None = None,
        model: str | None = None,
        manual: bool = False,
    ) -> list[ProviderRegistration]:
        required = _normalise_capabilities(required_capabilities)
        registrations = list(self.registrations)
        if provider_id is not None:
            registrations = [item for item in registrations if item.provider_id == provider_id]
        if model is not None:
            model_value = model.strip()
            registrations = [item for item in registrations if item.config.model == model_value]

        available: list[ProviderRegistration] = []
        for registration in registrations:
            config = registration.config
            health = self._effective_health(registration)
            if not config.enabled or not self.has_api_key(config):
                continue
            if manual and not config.allow_manual_selection:
                continue
            if not required.issubset(set(config.capabilities)):
                continue
            if health.status is not ProviderStatus.HEALTHY:
                continue
            available.append(ProviderRegistration(config, registration.provider, health))

        # Python 的排序是稳定的，因此同优先级保留清单文件顺序。
        available.sort(key=lambda item: item.config.priority, reverse=True)
        return available

    def select(
        self,
        required_capabilities: Iterable[ProviderCapability | str] | None = None,
        *,
        provider_id: str | None = None,
        model: str | None = None,
    ) -> ProviderRegistration:
        """选择一个可用 Provider；指定 providerId 时绝不静默切换。"""

        if provider_id is not None:
            registration = self.get_registration(provider_id)
            config = registration.config
            health = self._effective_health(registration)
            required = _normalise_capabilities(required_capabilities)
            if not config.enabled or not config.allow_manual_selection:
                raise ProviderSelectionError("PROVIDER_UNHEALTHY", "指定的供应商当前不可用")
            if not self.has_api_key(config):
                raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "指定的供应商未配置 API Key")
            if not required.issubset(set(config.capabilities)):
                raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "指定的供应商不支持当前能力")
            if health.status is ProviderStatus.RATE_LIMITED:
                raise ProviderSelectionError("PROVIDER_RATE_LIMITED", "指定的供应商当前受到限流")
            if health.status is not ProviderStatus.HEALTHY:
                raise ProviderSelectionError("PROVIDER_UNHEALTHY", "指定的供应商健康检查未通过")
            return ProviderRegistration(config, registration.provider, health)

        candidates = self.candidates(
            required_capabilities,
            model=model,
            manual=model is not None,
        )
        if not candidates:
            raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "没有满足能力要求的可用供应商")
        return candidates[0]

    # ``choose`` 是更直观的兼容别名。
    choose = select

    def available_providers(
        self,
        required_capabilities: Iterable[ProviderCapability | str] | None = None,
        *,
        model: str | None = None,
    ) -> list[ProviderRegistration]:
        """返回按优先级排序的可用候选。"""

        return self.candidates(required_capabilities, model=model)

    # 兼容常见命名，均保持同一过滤/排序语义。
    filter_by_capabilities = available_providers
    get_candidates = candidates

    def route(
        self,
        required_capabilities: Iterable[ProviderCapability | str] | None = None,
        *,
        provider_id: str | None = None,
        model: str | None = None,
    ) -> ProviderRegistration:
        return self.select(required_capabilities, provider_id=provider_id, model=model)

    def _initial_health(self, config: ProviderConfig) -> ProviderHealth:
        if not config.enabled:
            return ProviderHealth(status=ProviderStatus.DISABLED)
        if not self.has_api_key(config):
            return ProviderHealth(status=ProviderStatus.UNHEALTHY)
        return ProviderHealth(status=ProviderStatus.HEALTHY)

    def _effective_health(self, registration: ProviderRegistration) -> ProviderHealth:
        if not registration.config.enabled:
            return ProviderHealth(status=ProviderStatus.DISABLED, latency_ms=registration.health.latency_ms)
        if not self.has_api_key(registration.config):
            return ProviderHealth(status=ProviderStatus.UNHEALTHY, latency_ms=registration.health.latency_ms)
        return registration.health


@lru_cache(maxsize=1)
def get_provider_registry() -> ProviderRegistry:
    """应用级 Provider Registry 单例。"""

    return ProviderRegistry.from_file()


def clear_provider_registry_cache() -> None:
    get_provider_registry.cache_clear()


__all__ = [
    "ProviderRegistration",
    "ProviderRegistry",
    "ProviderSelectionError",
    "clear_provider_registry_cache",
    "get_provider_registry",
]
