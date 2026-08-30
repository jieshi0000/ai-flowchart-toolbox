import pytest

from app.providers.base import ModelProvider, ProviderPollResult, ProviderSubmission
from app.providers.provider_registry import ProviderRegistry, ProviderSelectionError
from app.schemas.provider import ProviderConfig, ProviderStatus
from tests.unit.provider_fixtures import provider_entry


class TestProviderRegistry:
    def _registry(self, monkeypatch):
        values = {"KEY_A": "present", "KEY_B": "present"}
        monkeypatch.setattr("app.providers.provider_registry.os.getenv", lambda key: values.get(key))
        configs = [
            ProviderConfig.model_validate(provider_entry("low", priority=1, key_env="KEY_A")),
            ProviderConfig.model_validate(provider_entry("high", priority=10, key_env="KEY_B")),
            ProviderConfig.model_validate(provider_entry("disabled", enabled=False)),
            ProviderConfig.model_validate(provider_entry("missing", key_env="KEY_MISSING")),
        ]
        return ProviderRegistry(configs, key_lookup=values.get)

    def test_filters_capabilities_and_orders_by_priority(self, monkeypatch):
        registry = self._registry(monkeypatch)
        selected = registry.select(["structured_output"])
        assert selected.provider_id == "high"
        assert [item.provider_id for item in registry.candidates(["text_generation"])] == ["high", "low"]

    def test_manual_selection_never_falls_back(self, monkeypatch):
        registry = self._registry(monkeypatch)
        with pytest.raises(ProviderSelectionError) as exc_info:
            registry.select(["text_generation"], provider_id="missing")
        assert exc_info.value.code == "PROVIDER_NOT_CONFIGURED"

    def test_public_info_is_safe_and_includes_health_status(self, monkeypatch):
        registry = self._registry(monkeypatch)
        infos = registry.public_infos()
        assert {item.provider_id for item in infos} == {"low", "high", "missing"}
        assert infos[-1].status is ProviderStatus.UNHEALTHY
        dumped = [item.model_dump(by_alias=True) for item in infos]
        assert all("baseUrl" not in item and "apiKeyEnv" not in item for item in dumped)

    @pytest.mark.asyncio
    async def test_refresh_health_uses_unified_provider_protocol(self):
        class HealthyProvider(ModelProvider):
            async def submit(self, request):
                return ProviderSubmission()

            async def poll(self, submission):
                return ProviderPollResult(status="succeeded")

            async def cancel(self, submission):
                return None

            async def health_check(self):
                from app.schemas.provider import ProviderHealth

                return ProviderHealth(status="healthy", latencyMs=12)

        values = {"KEY_A": "present"}
        config = ProviderConfig.model_validate(provider_entry("p", key_env="KEY_A"))
        registry = ProviderRegistry([config], providers={"p": HealthyProvider()}, key_lookup=values.get)
        await registry.refresh_health()
        assert registry.public_infos()[0].status is ProviderStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_aclose_releases_provider_resources(self):
        class ClosableProvider(ModelProvider):
            def __init__(self):
                self.closed = False

            async def submit(self, request):
                return ProviderSubmission(result={})

            async def poll(self, submission):
                return ProviderPollResult(status="succeeded", result={})

            async def cancel(self, submission):
                return None

            async def health_check(self):
                from app.schemas.provider import ProviderHealth

                return ProviderHealth(status="healthy")

            async def aclose(self):
                self.closed = True

        values = {"KEY_A": "present"}
        config = ProviderConfig.model_validate(provider_entry("p", key_env="KEY_A"))
        provider = ClosableProvider()
        registry = ProviderRegistry([config], providers={"p": provider}, key_lookup=values.get)

        await registry.aclose()

        assert provider.closed is True

    def test_adapter_factory_without_key_lookup_remains_supported(self):
        class SimpleProvider(ModelProvider):
            async def submit(self, request):
                return ProviderSubmission(result={})

            async def poll(self, submission):
                return ProviderPollResult(status="succeeded", result={})

            async def cancel(self, submission):
                return None

            async def health_check(self):
                from app.schemas.provider import ProviderHealth

                return ProviderHealth(status="healthy")

        values = {"KEY_A": "present"}
        config = ProviderConfig.model_validate(provider_entry("p", key_env="KEY_A"))
        registry = ProviderRegistry([config], key_lookup=values.get)
        registry.register_adapter("openai_compatible", lambda provider_config: SimpleProvider())

        assert isinstance(registry.build_provider("p"), SimpleProvider)
