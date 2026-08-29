import json

import httpx
import pytest

from app.providers.openai_responses import OPENAI_RESPONSES_PATH, OpenAIResponsesProvider
from app.providers.provider_registry import ProviderRegistry
from app.providers.transport import (
    HttpxTransport,
    ProviderHTTPError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.schemas.provider import ProviderConfig, ProviderStatus
from tests.unit.provider_fixtures import provider_entry


def _responses_config(**overrides) -> ProviderConfig:
    payload = provider_entry(
        "deepseek-responses-test",
        key_env="DEEPSEEK_TEST_KEY",
        adapter="openai_compatible",
        protocol="openai_responses",
        baseUrl="https://api.deepseek.com",
        model="deepseek-v4-flash",
        displayName="deepseek-v4-flash",
        maxOutputTokens=1234,
    )
    payload.update(overrides)
    return ProviderConfig.model_validate(payload)


def _diagram() -> dict:
    return {
        "title": "请假审批流程",
        "direction": "TB",
        "nodes": [
            {"id": "start", "type": "start", "label": "提交申请"},
            {"id": "end", "type": "end", "label": "审批完成"},
        ],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }


def _response(*, output_text: str | None = None, status: str = "completed", **fields) -> dict:
    value = {
        "id": "resp_test_123",
        "object": "response",
        "status": status,
        "output": [],
    }
    if output_text is not None:
        value["output_text"] = output_text
    value.update(fields)
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "expected_path"),
    [
        ("https://api.deepseek.com", "/responses"),
        ("https://api.openai.com/v1", "/v1/responses"),
        ("https://relay.example/gateway/v1", "/gateway/v1/responses"),
    ],
)
async def test_responses_supports_deepseek_openai_and_relay_payloads(base_url, expected_path):
    seen: dict = {}

    async def handler(request: httpx.Request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["idempotency_key"] = request.headers.get("idempotency-key")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_response(output_text=json.dumps(_diagram())), request=request)

    config = _responses_config(baseUrl=base_url)
    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIResponsesProvider(
            config,
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        submission = await provider.submit(
            {
                "prompt": "员工提交请假申请，主管审批",
                "direction": "TB",
                "idempotencyKey": "generation-123",
                # 这些字段来自其他 Responses 语义，不能被转发给 DeepSeek。
                "previous_response_id": "resp_old",
                "conversation": "conv_old",
                "store": True,
                "background": True,
                "metadata": {"private": "value"},
                "include": ["reasoning.encrypted_content"],
                "truncation": "auto",
                "context_management": {"compact_threshold": 100},
                "stream_options": {"include_usage": True},
            }
        )

    assert seen["method"] == "POST"
    assert seen["path"] == expected_path
    assert seen["authorization"] == "Bearer test-key"
    assert seen["idempotency_key"] == "generation-123"
    payload = seen["payload"]
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["max_output_tokens"] == 1234
    assert payload["stream"] is False
    assert "只返回一个严格合法的 JSON 对象" in payload["instructions"]
    assert "流程图方向必须是 TB" in payload["input"]
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["name"] == "diagram_document"
    assert payload["text"]["format"]["strict"] is True
    if base_url == "https://api.deepseek.com":
        assert payload["reasoning"] == {"effort": "none"}
        assert set(payload) == {
            "model",
            "instructions",
            "input",
            "max_output_tokens",
            "stream",
            "text",
            "reasoning",
        }
    else:
        assert "reasoning" not in payload
        assert set(payload) == {"model", "instructions", "input", "max_output_tokens", "stream", "text"}
    assert submission.provider_request_id == "resp_test_123"
    assert submission.mode == "sync"
    assert submission.status == "succeeded"
    assert submission.result["mermaidSource"].startswith("flowchart TB")


def test_responses_maps_deep_thinking_switch_for_deepseek_only():
    provider = OpenAIResponsesProvider(
        _responses_config(),
        key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
    )

    assert provider._build_request_payload({"prompt": "生成流程"})["reasoning"] == {"effort": "none"}
    assert provider._build_request_payload({"prompt": "生成流程", "deepThinking": True})["reasoning"] == {
        "effort": "high"
    }

    relay = OpenAIResponsesProvider(
        _responses_config(baseUrl="https://relay.example/v1"),
        key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
    )
    assert "reasoning" not in relay._build_request_payload({"prompt": "生成流程", "deepThinking": True})


@pytest.mark.asyncio
async def test_relay_without_structured_capability_uses_json_prompt_fallback():
    async def handler(request: httpx.Request):
        payload = json.loads(request.content)
        assert "text" not in payload
        assert "只返回一个严格合法的 JSON 对象" in payload["instructions"]
        return httpx.Response(200, json=_response(output_text=json.dumps(_diagram())), request=request)

    config = _responses_config(
        providerId="relay-responses-test",
        baseUrl="https://relay.example/api",
        capabilities=["text_generation"],
    )
    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIResponsesProvider(
            config,
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "relay-key"}.get,
        )
        submission = await provider.submit({"prompt": "生成审批流程"})

    assert submission.result["title"] == "请假审批流程"


@pytest.mark.asyncio
async def test_responses_extracts_output_items_when_output_text_is_missing():
    response = _response(
        output=[
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(_diagram())}],
            }
        ]
    )

    async def handler(request: httpx.Request):
        return httpx.Response(200, json=response, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIResponsesProvider(
            _responses_config(),
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        submission = await provider.submit({"prompt": "生成审批流程"})

    assert submission.result["title"] == "请假审批流程"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (_response(status="incomplete", incomplete_details={"reason": "max_output_tokens"}), "PROVIDER_SUBMIT_FAILED"),
        (_response(status="completed", output=[{"type": "message", "content": [{"type": "refusal", "refusal": "不安全"}]}]), "PROVIDER_SUBMIT_FAILED"),
        (_response(output_text="```json\n{not-json}\n```"), "DIAGRAM_SCHEMA_INVALID"),
    ],
)
async def test_responses_rejects_incomplete_refused_and_invalid_results(response, expected_code):
    async def handler(request: httpx.Request):
        return httpx.Response(200, json=response, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIResponsesProvider(
            _responses_config(),
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        with pytest.raises(ProviderResponseError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.code == expected_code
    assert exc_info.value.fallback_allowed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_code", "fallback_allowed"),
    [
        (429, "PROVIDER_RATE_LIMITED", True),
        (503, "PROVIDER_UNHEALTHY", True),
    ],
)
async def test_responses_preserves_safe_http_fallback_mapping(status_code, expected_code, fallback_allowed):
    async def handler(request: httpx.Request):
        return httpx.Response(status_code, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIResponsesProvider(
            _responses_config(),
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        with pytest.raises(ProviderHTTPError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.code == expected_code
    assert exc_info.value.fallback_allowed is fallback_allowed


@pytest.mark.asyncio
async def test_responses_timeout_is_not_safe_for_automatic_fallback():
    async def handler(request: httpx.Request):
        raise httpx.ReadTimeout("timed out", request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIResponsesProvider(
            _responses_config(),
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.fallback_allowed is False


@pytest.mark.asyncio
async def test_registry_builds_responses_adapter_by_protocol():
    config = _responses_config(baseUrl="https://api.openai.com/v1")
    registry = ProviderRegistry([config], key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get)
    registry.register_adapter("openai_compatible", OpenAIResponsesProvider, protocol="openai_responses")

    async def handler(request: httpx.Request):
        assert request.url.path == "/v1/responses"
        return httpx.Response(200, json=_response(output_text=json.dumps(_diagram())), request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = registry.build_provider("deepseek-responses-test", transport=transport)
        assert isinstance(provider, OpenAIResponsesProvider)
        submission = await provider.submit({"prompt": "生成审批流程"})

    assert submission.status == "succeeded"
    assert (await provider.health_check()).status is ProviderStatus.HEALTHY
    assert OPENAI_RESPONSES_PATH == "/v1/responses"
