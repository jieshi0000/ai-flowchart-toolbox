import json

import httpx
import pytest

from app.providers.anthropic import ANTHROPIC_API_VERSION, DIAGRAM_TOOL_NAME, AnthropicMessagesProvider
from app.providers.base import ProviderSubmission
from app.providers.provider_registry import ProviderRegistry
from app.providers.transport import HttpxTransport, ProviderHTTPError, ProviderResponseError, ProviderTimeoutError
from app.schemas.provider import ProviderConfig, ProviderStatus
from tests.unit.provider_fixtures import provider_entry


def _anthropic_config(**overrides) -> ProviderConfig:
    payload = provider_entry(
        "anthropic-test",
        key_env="ANTHROPIC_TEST_KEY",
        adapter="anthropic",
        protocol="anthropic_messages",
        baseUrl="https://anthropic.example",
        model="claude-test",
        displayName="claude-test",
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


def _message_response(content, *, stop_reason="tool_use") -> dict:
    return {
        "id": "msg_test_123",
        "type": "message",
        "role": "assistant",
        "stop_reason": stop_reason,
        "content": content,
    }


@pytest.mark.asyncio
async def test_anthropic_messages_submit_uses_tool_schema_and_returns_valid_document():
    seen = {}

    async def handler(request: httpx.Request):
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["api_key"] = request.headers.get("x-api-key")
        seen["version"] = request.headers.get("anthropic-version")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=_message_response(
                [{"type": "tool_use", "id": "toolu_1", "name": DIAGRAM_TOOL_NAME, "input": _diagram()}]
            ),
            request=request,
        )

    config = _anthropic_config()
    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = AnthropicMessagesProvider(config, transport=transport, key_lookup={"ANTHROPIC_TEST_KEY": "test-key"}.get)
        submission = await provider.submit({"prompt": "员工提交请假申请，主管审批", "direction": "TB"})

    assert seen["path"] == "/v1/messages"
    assert seen["authorization"] is None
    assert seen["api_key"] == "test-key"
    assert seen["version"] == ANTHROPIC_API_VERSION
    assert seen["payload"]["model"] == "claude-test"
    assert seen["payload"]["max_tokens"] == 1234
    assert seen["payload"]["tool_choice"] == {
        "type": "tool",
        "name": DIAGRAM_TOOL_NAME,
        "disable_parallel_tool_use": True,
    }
    tool = seen["payload"]["tools"][0]
    assert tool["name"] == DIAGRAM_TOOL_NAME
    assert {"title", "direction", "nodes", "edges"} <= set(tool["input_schema"]["properties"])
    assert "流程图方向必须是 TB" in seen["payload"]["messages"][0]["content"]
    assert submission.provider_request_id == "msg_test_123"
    assert submission.mode == "sync"
    assert submission.status == "succeeded"
    assert submission.result["title"] == "请假审批流程"
    assert submission.result["mermaidSource"].startswith("flowchart TB")


@pytest.mark.asyncio
async def test_anthropic_messages_accepts_a_single_markdown_json_fallback():
    diagram = _diagram()
    diagram["nodes"][0]["label"] = "无法提交时结束流程"

    async def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json=_message_response([{"type": "text", "text": f"```json\n{json.dumps(diagram)}\n```"}], stop_reason="end_turn"),
            request=request,
        )

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = AnthropicMessagesProvider(
            _anthropic_config(), transport=transport, key_lookup={"ANTHROPIC_TEST_KEY": "test-key"}.get
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
async def test_anthropic_messages_preserves_unified_http_error_mapping(
    status_code, headers, expected_code, retryable, fallback_allowed
):
    async def handler(request: httpx.Request):
        return httpx.Response(status_code, headers=headers, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = AnthropicMessagesProvider(
            _anthropic_config(), transport=transport, key_lookup={"ANTHROPIC_TEST_KEY": "test-key"}.get
        )
        with pytest.raises(ProviderHTTPError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    assert exc_info.value.fallback_allowed is fallback_allowed
    if status_code == 429:
        assert exc_info.value.retry_after_seconds == 9


@pytest.mark.asyncio
async def test_anthropic_messages_preserves_timeout_mapping():
    async def handler(request: httpx.Request):
        raise httpx.ReadTimeout("timed out", request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = AnthropicMessagesProvider(
            _anthropic_config(), transport=transport, key_lookup={"ANTHROPIC_TEST_KEY": "test-key"}.get
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
        (_message_response([{"type": "text", "text": "抱歉，我不能处理这个请求。"}], stop_reason="refusal"), "PROVIDER_SUBMIT_FAILED"),
        (_message_response([], stop_reason="end_turn"), "PROVIDER_SUBMIT_FAILED"),
        (_message_response([{"type": "text", "text": "```json\n{not-json}\n```"}], stop_reason="end_turn"), "DIAGRAM_SCHEMA_INVALID"),
        (
            _message_response(
                [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": DIAGRAM_TOOL_NAME,
                        "input": {"title": "bad", "unexpected": True},
                    }
                ]
            ),
            "DIAGRAM_SCHEMA_INVALID",
        ),
    ],
)
async def test_anthropic_messages_rejects_refusals_empty_and_invalid_results(response, expected_code):
    async def handler(request: httpx.Request):
        return httpx.Response(200, json=response, request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = AnthropicMessagesProvider(
            _anthropic_config(), transport=transport, key_lookup={"ANTHROPIC_TEST_KEY": "test-key"}.get
        )
        with pytest.raises(ProviderResponseError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is False
    assert exc_info.value.fallback_allowed is False


@pytest.mark.asyncio
async def test_anthropic_messages_rejects_invalid_http_json_response():
    async def handler(request: httpx.Request):
        return httpx.Response(200, content=b"{not-json", request=request)

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = AnthropicMessagesProvider(
            _anthropic_config(), transport=transport, key_lookup={"ANTHROPIC_TEST_KEY": "test-key"}.get
        )
        with pytest.raises(ProviderResponseError) as exc_info:
            await provider.submit({"prompt": "生成审批流程"})

    assert exc_info.value.code == "PROVIDER_SUBMIT_FAILED"
    assert exc_info.value.fallback_allowed is False


@pytest.mark.asyncio
async def test_anthropic_provider_registry_factory_and_sync_protocol():
    config = _anthropic_config(baseUrl="https://anthropic.example/v1")
    values = {"ANTHROPIC_TEST_KEY": "test-key"}
    registry = ProviderRegistry([config], key_lookup=values.get)
    registry.register_adapter("anthropic", AnthropicMessagesProvider)

    async def handler(request: httpx.Request):
        assert request.url.path == "/v1/messages"
        return httpx.Response(
            200,
            json=_message_response(
                [{"type": "tool_use", "id": "toolu_1", "name": DIAGRAM_TOOL_NAME, "input": _diagram()}]
            ),
            request=request,
        )

    async with HttpxTransport(transport=httpx.MockTransport(handler)) as transport:
        provider = registry.build_provider("anthropic-test", transport=transport)
        assert isinstance(provider, AnthropicMessagesProvider)
        submission = await provider.submit({"prompt": "生成审批流程"})
        polled = await provider.poll(submission)
        await provider.cancel(submission)

    assert polled.status == "succeeded"
    assert polled.result == submission.result
    assert (await provider.health_check()).status is ProviderStatus.HEALTHY
    missing_key_provider = AnthropicMessagesProvider(config, key_lookup={}.get)
    assert (await missing_key_provider.health_check()).status is ProviderStatus.UNHEALTHY
