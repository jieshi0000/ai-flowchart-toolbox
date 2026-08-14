import json

import httpx
import pytest

from app.providers.transport import (
    HttpxTransport,
    ProviderHTTPError,
    ProviderTimeoutError,
    redact_sensitive,
)


@pytest.mark.asyncio
async def test_httpx_transport_success_and_auth_header():
    seen = {}

    async def handler(request: httpx.Request):
        seen["authorization"] = request.headers.get("authorization")
        seen["request_id"] = request.headers.get("x-request-id")
        return httpx.Response(200, json={"ok": True}, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        result = await transport.post_json(
            "https://provider.example/v1/chat",
            api_key="test-key",
            payload={"prompt": "safe"},
        )
    assert result == {"ok": True}
    assert seen["authorization"] == "Bearer test-key"
    assert seen["request_id"]


@pytest.mark.asyncio
async def test_httpx_transport_maps_timeout_and_rate_limit():
    async def timeout_handler(request: httpx.Request):
        raise httpx.ReadTimeout("timed out", request=request)

    async with HttpxTransport(transport=httpx.MockTransport(timeout_handler)) as transport:
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await transport.get_json("https://provider.example/health")
    assert exc_info.value.code == "PROVIDER_TASK_TIMEOUT"
    assert exc_info.value.fallback_allowed is False

    async def rate_limit_handler(request: httpx.Request):
        return httpx.Response(429, headers={"Retry-After": "7"}, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(rate_limit_handler)) as transport:
        with pytest.raises(ProviderHTTPError) as exc_info:
            await transport.get_json("https://provider.example/health")
    assert exc_info.value.code == "PROVIDER_RATE_LIMITED"
    assert exc_info.value.retry_after_seconds == 7


@pytest.mark.asyncio
async def test_httpx_transport_logs_do_not_contain_key_or_base_url():
    class Recorder:
        def __init__(self):
            self.calls = []

        def info(self, *args):
            self.calls.append(args)

        def warning(self, *args):
            self.calls.append(args)

    recorder = Recorder()

    async def handler(request: httpx.Request):
        return httpx.Response(200, json={"ok": True}, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler), logger_=recorder) as transport:
        await transport.get_json("https://private.provider.example/v1/models", api_key="test-key")
    output = str(recorder.calls)
    assert "test-key" not in output
    assert "private.provider.example" not in output


def test_redaction_removes_secret_and_base_url():
    redacted = redact_sensitive(
        {"Authorization": "Bearer test-key", "baseUrl": "https://provider.example", "nested": "test-key"},
        secrets=["test-key"],
    )
    text = json.dumps(redacted, ensure_ascii=False)
    assert "test-key" not in text
    assert "provider.example" not in text
