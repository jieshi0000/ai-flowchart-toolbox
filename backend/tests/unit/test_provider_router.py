import pytest

from app.providers.base import ModelProvider, ProviderPollResult, ProviderSubmission
from app.providers.provider_router import ProviderRouter
from app.providers.provider_registry import ProviderRegistry, ProviderSelectionError
from app.providers.transport import ProviderHTTPError, ProviderResponseError
from app.schemas.provider import ProviderConfig, ProviderHealth
from tests.unit.provider_fixtures import provider_entry


class StubProvider(ModelProvider):
    def __init__(self, *, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    async def submit(self, request):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ProviderSubmission(provider_request_id="stub-request", result=self.result or {"ok": True})

    async def poll(self, submission):
        return ProviderPollResult(status="succeeded", result=submission.result)

    async def cancel(self, submission):
        return None

    async def health_check(self):
        return ProviderHealth(status="healthy")


def _config(provider_id: str, *, priority: int, model: str = "model-a") -> ProviderConfig:
    return ProviderConfig.model_validate(
        provider_entry(
            provider_id,
            key_env=f"{provider_id.upper()}_KEY",
            priority=priority,
            model=model,
            displayName=model,
        )
    )


def _registry(high: StubProvider, low: StubProvider) -> ProviderRegistry:
    values = {"HIGH_KEY": "high-key", "LOW_KEY": "low-key"}
    return ProviderRegistry(
        [
            _config("high", priority=100),
            _config("low", priority=10),
        ],
        providers={"high": high, "low": low},
        key_lookup=values.get,
    )


@pytest.mark.asyncio
async def test_router_uses_priority_and_falls_back_once_for_retryable_failure():
    high = StubProvider(error=ProviderHTTPError(503))
    low = StubProvider(result={"provider": "low"})
    result = await _registry(high, low).submit_with_fallback({"prompt": "生成流程"})

    assert result.provider_id == "low"
    assert result.fallback_from == "high"
    assert result.fallback_reason == "PROVIDER_UNHEALTHY"
    assert result.attempts == ("high", "low")
    assert high.calls == 1
    assert low.calls == 1


@pytest.mark.asyncio
async def test_router_does_not_fallback_after_schema_failure():
    high = StubProvider(error=ProviderResponseError("结构无效", code="DIAGRAM_SCHEMA_INVALID"))
    low = StubProvider(result={"provider": "low"})
    with pytest.raises(ProviderResponseError) as exc_info:
        await ProviderRouter(_registry(high, low)).submit({"prompt": "生成流程"})

    assert exc_info.value.code == "DIAGRAM_SCHEMA_INVALID"
    assert high.calls == 1
    assert low.calls == 0


@pytest.mark.asyncio
async def test_router_manual_provider_never_switches_to_other_provider():
    high = StubProvider(error=ProviderHTTPError(429))
    low = StubProvider(result={"provider": "low"})
    router = ProviderRouter(_registry(high, low))

    with pytest.raises(ProviderHTTPError):
        await router.submit({"prompt": "生成流程"}, provider_id="high")

    assert high.calls == 1
    assert low.calls == 0


@pytest.mark.asyncio
async def test_router_rejects_manual_model_when_no_matching_candidate():
    high = StubProvider(result={"provider": "high"})
    low = StubProvider(result={"provider": "low"})
    router = ProviderRouter(_registry(high, low))

    with pytest.raises(ProviderSelectionError) as exc_info:
        await router.submit({"prompt": "生成流程"}, model="unknown-model")

    assert exc_info.value.code == "PROVIDER_NOT_CONFIGURED"
    assert high.calls == 0
    assert low.calls == 0
