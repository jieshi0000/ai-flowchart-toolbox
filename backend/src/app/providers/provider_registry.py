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
    ProviderProtocol,
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


def _factory_accepts_keyword(factory: Callable[..., ModelProvider], name: str) -> bool:
    """判断适配器工厂是否声明了可选构造参数，保留旧工厂兼容性。"""

    try:
        parameters = inspect.signature(factory).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == name or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


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
        self._protocol_adapter_factories: dict[tuple[str, str], Callable[..., ModelProvider]] = {}
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

    def register_adapter(
        self,
        adapter: str,
        factory: Callable[..., ModelProvider],
        *,
        protocol: ProviderProtocol | str | None = None,
    ) -> None:
        """注册适配器工厂，可按协议区分同一兼容适配器。"""

        normalized = str(adapter).strip()
        if not normalized:
            raise ValueError("adapter 不能为空")
        if protocol is None:
            self._adapter_factories[normalized] = factory
            return
        normalized_protocol = (
            protocol.value if isinstance(protocol, ProviderProtocol) else str(protocol).strip()
        )
        if not normalized_protocol:
            raise ValueError("protocol 不能为空")
        self._protocol_adapter_factories[(normalized, normalized_protocol)] = factory

    def register_protocol_adapter(
        self,
        adapter: str,
        protocol: ProviderProtocol | str,
        factory: Callable[..., ModelProvider],
    ) -> None:
        """显式注册某个 adapter + protocol 的构造工厂。"""

        self.register_adapter(adapter, factory, protocol=protocol)

    def build_provider(self, provider_id: str, **kwargs: Any) -> ModelProvider:
        registration = self.get_registration(provider_id)
        if registration.provider is not None:
            return registration.provider
        factory = self._protocol_adapter_factories.get(
            (registration.config.adapter.value, registration.config.protocol.value)
        )
        if factory is None:
            factory = self._adapter_factories.get(registration.config.adapter.value)
        if factory is None:
            raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "当前供应商适配器尚未注册")
        factory_kwargs = dict(kwargs)
        if "key_lookup" not in factory_kwargs and _factory_accepts_keyword(factory, "key_lookup"):
            factory_kwargs["key_lookup"] = self._key_lookup
        provider = factory(registration.config, **factory_kwargs)
        self.register_provider(provider_id, provider)
        return provider

    async def aclose(self) -> None:
        """关闭由注册中心持有且支持异步关闭的 Provider。"""

        for registration in self.registrations:
            provider = registration.provider
            close = getattr(provider, "aclose", None)
            if close is None:
                continue
            result = close()
            if inspect.isawaitable(result):
                await result

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
            if model is not None and config.model != model.strip():
                raise ProviderSelectionError("PROVIDER_NOT_CONFIGURED", "指定的供应商与模型不匹配")
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

    async def submit_with_fallback(
        self,
        request: Mapping[str, Any],
        required_capabilities: Iterable[ProviderCapability | str] | None = (
            ProviderCapability.TEXT_GENERATION,
        ),
        *,
        provider_id: str | None = None,
        model: str | None = None,
        **provider_kwargs: Any,
    ):
        """提交一次生成请求，并按安全规则最多切换一个候选供应商。"""

        from app.providers.provider_router import ProviderRouter

        return await ProviderRouter(self).submit(
            request,
            required_capabilities,
            provider_id=provider_id,
            model=model,
            **provider_kwargs,
        )

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

    registry = ProviderRegistry.from_file()
    # 适配器按协议注册，避免 openai_compatible 配置被错误地交给另一种协议。
    from app.providers.anthropic import AnthropicMessagesProvider
    from app.providers.openai_chat import OpenAIChatCompletionsProvider
    from app.providers.openai_responses import OpenAIResponsesProvider

    registry.register_adapter(
        "anthropic",
        AnthropicMessagesProvider,
        protocol=ProviderProtocol.ANTHROPIC_MESSAGES,
    )
    registry.register_adapter(
        "openai_compatible",
        OpenAIChatCompletionsProvider,
        protocol=ProviderProtocol.OPENAI_CHAT_COMPLETIONS,
    )
    registry.register_adapter(
        "openai_compatible",
        OpenAIResponsesProvider,
        protocol=ProviderProtocol.OPENAI_RESPONSES,
    )
    return registry


def clear_provider_registry_cache() -> None:
    get_provider_registry.cache_clear()


async def close_provider_registry() -> None:
    """仅在单例已被使用时关闭其 HTTP 等运行时资源。"""

    if get_provider_registry.cache_info().currsize:
        await get_provider_registry().aclose()
    clear_provider_registry_cache()


__all__ = [
    "ProviderRegistration",
    "ProviderRegistry",
    "ProviderSelectionError",
    "clear_provider_registry_cache",
    "close_provider_registry",
    "get_provider_registry",
]
