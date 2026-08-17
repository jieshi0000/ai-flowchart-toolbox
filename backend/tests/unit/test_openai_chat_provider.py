import json

import httpx
import pytest

from app.providers.openai_chat import OPENAI_CHAT_COMPLETIONS_PATH, OpenAIChatCompletionsProvider
from app.providers.provider_registry import ProviderRegistry
from app.providers.transport import HttpxTransport, ProviderHTTPError, ProviderResponseError, ProviderTimeoutError
from app.schemas.provider import ProviderConfig, ProviderStatus
from tests.unit.provider_fixtures import provider_entry


def _openai_chat_config(**overrides) -> ProviderConfig:
    payload = provider_entry(
        "deepseek-chat-test",
        key_env="DEEPSEEK_TEST_KEY",
        adapter="openai_compatible",
        protocol="openai_chat_completions",
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


def _chat_response(content: str | None, *, finish_reason: str | None = "stop", **message_fields) -> dict:
    return {
        "id": "chatcmpl_test_123",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content, **message_fields},
                "finish_reason": finish_reason,
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "expected_path", "expected_response_format"),
    [
        ("https://api.deepseek.com", "/chat/completions", "json_object"),
        ("https://api.openai.com/v1", "/v1/chat/completions", "json_schema"),
        ("https://gateway.example/custom/v1", "/custom/v1/chat/completions", "json_object"),
    ],
)
async def test_openai_chat_reuses_one_adapter_for_deepseek_openai_and_compatible_base_urls(
    base_url, expected_path, expected_response_format
):
    seen = {}

    async def handler(request: httpx.Request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["idempotency_key"] = request.headers.get("idempotency-key")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_chat_response(json.dumps(_diagram())), request=request)

    config = _openai_chat_config(baseUrl=base_url)
    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIChatCompletionsProvider(
            config,
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        submission = await provider.submit(
            {
                "prompt": "员工提交请假申请，主管审批",
                "direction": "TB",
                "idempotencyKey": "generation-123",
            }
        )

    assert seen["method"] == "POST"
    assert seen["path"] == expected_path
    assert seen["authorization"] == "Bearer test-key"
    assert seen["idempotency_key"] == "generation-123"
    assert seen["payload"]["model"] == "deepseek-v4-flash"
    assert seen["payload"]["max_tokens"] == 1234
    assert seen["payload"]["stream"] is False
    assert "只返回一个严格合法的 JSON 对象" in seen["payload"]["messages"][0]["content"]
    assert "流程图方向必须是 TB" in seen["payload"]["messages"][1]["content"]
    assert seen["payload"]["response_format"]["type"] == expected_response_format
    if expected_response_format == "json_schema":
        schema = seen["payload"]["response_format"]["json_schema"]
        assert schema["name"] == "diagram_document"
        assert schema["strict"] is True
        assert set(schema["schema"]["required"]) == set(schema["schema"]["properties"])
        assert set(schema["schema"]["$defs"]["DiagramNode"]["required"]) == set(
            schema["schema"]["$defs"]["DiagramNode"]["properties"]
        )
    else:
        assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert submission.provider_request_id == "chatcmpl_test_123"
    assert submission.mode == "sync"
    assert submission.status == "succeeded"
    assert submission.result["title"] == "请假审批流程"
    assert submission.result["mermaidSource"].startswith("flowchart TB")


@pytest.mark.asyncio
async def test_openai_chat_accepts_a_single_markdown_json_fallback():
    diagram = _diagram()
    diagram["nodes"][0]["label"] = "无法提交时结束流程"

    async def handler(request: httpx.Request):
        return httpx.Response(200, json=_chat_response(f"```json\n{json.dumps(diagram)}\n```"), request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIChatCompletionsProvider(
            _openai_chat_config(),
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        submission = await provider.submit({"prompt": "生成审批流程"})

    assert submission.result["title"] == "请假审批流程"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "headers", "expected_code", "retryable", "fallback_allowed"),
    [
        (401, {}, "PROVIDER_AUTH_FAILED", False, False),
        (429, {"Retry-After": "9"}, "PROVIDER_RATE_LIMITED", True, True),
        (503, {}, "PROVIDER_UNHEALTHY", True, True),
    ],
)
async def test_openai_chat_preserves_unified_http_error_mapping(
    status_code, headers, expected_code, retryable, fallback_allowed
):
    async def handler(request: httpx.Request):
        return httpx.Response(status_code, headers=headers, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIChatCompletionsProvider(
            _openai_chat_config(),
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        with pytest.raises(ProviderHTTPError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    assert exc_info.value.fallback_allowed is fallback_allowed
    if status_code == 429:
        assert exc_info.value.retry_after_seconds == 9


@pytest.mark.asyncio
async def test_openai_chat_preserves_timeout_mapping():
    async def handler(request: httpx.Request):
        raise httpx.ReadTimeout("timed out", request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIChatCompletionsProvider(
            _openai_chat_config(),
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.code == "PROVIDER_TASK_TIMEOUT"
    assert exc_info.value.retryable is True
    assert exc_info.value.fallback_allowed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (_chat_response(json.dumps(_diagram()), finish_reason="length"), "PROVIDER_SUBMIT_FAILED"),
        (_chat_response(None, finish_reason="content_filter"), "PROVIDER_SUBMIT_FAILED"),
        (_chat_response(None, refusal="内容不安全"), "PROVIDER_SUBMIT_FAILED"),
        ({"id": "chatcmpl_test_123", "choices": []}, "PROVIDER_SUBMIT_FAILED"),
        (_chat_response("```json\n{not-json}\n```"), "DIAGRAM_SCHEMA_INVALID"),
        (_chat_response(json.dumps({"title": "bad", "unexpected": True})), "DIAGRAM_SCHEMA_INVALID"),
    ],
)
async def test_openai_chat_rejects_incomplete_refused_empty_and_invalid_results(response, expected_code):
    async def handler(request: httpx.Request):
        return httpx.Response(200, json=response, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIChatCompletionsProvider(
            _openai_chat_config(),
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        with pytest.raises(ProviderResponseError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is False
    assert exc_info.value.fallback_allowed is False


@pytest.mark.asyncio
async def test_openai_chat_rejects_invalid_http_json_response():
    async def handler(request: httpx.Request):
        return httpx.Response(200, content=b"{not-json", request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = OpenAIChatCompletionsProvider(
            _openai_chat_config(),
            transport=transport,
            key_lookup={"DEEPSEEK_TEST_KEY": "test-key"}.get,
        )
        with pytest.raises(ProviderResponseError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.code == "PROVIDER_SUBMIT_FAILED"
    assert exc_info.value.fallback_allowed is False


@pytest.mark.asyncio
async def test_openai_chat_provider_registry_factory_and_sync_protocol():
    config = _openai_chat_config(baseUrl="https://api.openai.com/v1")
    values = {"DEEPSEEK_TEST_KEY": "test-key"}
    registry = ProviderRegistry([config], key_lookup=values.get)
    registry.register_adapter("openai_compatible", OpenAIChatCompletionsProvider)

    async def handler(request: httpx.Request):
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json=_chat_response(json.dumps(_diagram())), request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = registry.build_provider("deepseek-chat-test", transport=transport)
        assert isinstance(provider, OpenAIChatCompletionsProvider)
        submission = await provider.submit({"prompt": "生成审批流程"})
        polled = await provider.poll(submission)
        await provider.cancel(submission)

    assert polled.status == "succeeded"
    assert polled.result == submission.result
    assert (await provider.health_check()).status is ProviderStatus.HEALTHY
    missing_key_provider = OpenAIChatCompletionsProvider(config, key_lookup={}.get)
    assert (await missing_key_provider.health_check()).status is ProviderStatus.UNHEALTHY
    assert OPENAI_CHAT_COMPLETIONS_PATH == "/v1/chat/completions"
