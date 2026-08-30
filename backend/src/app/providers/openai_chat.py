"""OpenAI Chat Completions 兼容适配器。

DeepSeek Chat、OpenAI 官方 Chat 和遵循同一协议的中转站都通过本模块接入。
模型返回的内容始终先解析为 JSON，再经过 DiagramDocument 与 Mermaid 编译边界校验。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.providers.base import ModelProvider, ProviderPollResult, ProviderSubmission
from app.providers.generation_prompt import build_generation_prompt, is_thinking_enabled
from app.providers.transport import HttpxTransport, ProviderResponseError, ProviderTransportError
from app.schemas.diagram import DiagramDocument, DiagramGenerationResult
from app.schemas.provider import (
    ProviderAdapter,
    ProviderConfig,
    ProviderHealth,
    ProviderProtocol,
    ProviderStatus,
)
from app.services.diagram_service import compile_generated_diagram_document


OPENAI_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

_SYSTEM_PROMPT = (
    "根据用户描述生成逻辑清晰、便于阅读的流程图。只返回一个严格合法的 JSON 对象，不要使用 Markdown 代码块、"
    "HTML、脚本、解释或思维过程。JSON 必须只包含 title、direction、nodes、edges 和 mermaidSource；"
    "你必须根据流程层级、分支和阅读顺序，在 TB（自上而下）与 LR（从左到右）之间选择 direction。"
    "nodes 中每项包含 id、type、label，type 只能是 "
    "start、end、process、decision、input_output 或 subprocess；edges 中每项包含 id、source、target，"
    "可选 label 或 condition。mermaidSource 必须表达与 JSON 相同的流程，第一行必须严格为 "
    "flowchart TB 或 flowchart LR；按 nodes 数组顺序使用 n0、n1 等别名，每个节点和连线单独一行，"
    "连线标签只能写成 -->|文本|；禁止 HTML、注释、初始化指令、click、style、class、link 或其他交互、样式和外部引用语法。"
    "如果用户提供了生成粒度或配色约束，必须严格遵守这些约束。"
)
_JSON_CODE_BLOCK_RE = re.compile(
    r"\A\s*```(?:json)?\s*(\{.*\})\s*```\s*\Z",
    re.IGNORECASE | re.DOTALL,
)
_REFUSAL_TEXT_RE = re.compile(
    r"(?:\bi(?:'m| am) sorry\b|\bi cannot\b|\bi can't\b|\bunable to\b|"
    r"\bcan't help\b|抱歉|无法|不能|拒绝)",
    re.IGNORECASE,
)
_REFUSAL_FINISH_REASONS = frozenset({"content_filter", "content_filtered", "refusal", "safety"})


class OpenAIChatCompletionsProvider(ModelProvider):
    """将统一 Provider 请求转换为 OpenAI Chat Completions 请求。"""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: HttpxTransport | None = None,
        key_lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        if config.adapter is not ProviderAdapter.OPENAI_COMPATIBLE:
            raise ValueError("OpenAIChatCompletionsProvider 只能使用 openai_compatible adapter 配置")
        if config.protocol is not ProviderProtocol.OPENAI_CHAT_COMPLETIONS:
            raise ValueError("OpenAIChatCompletionsProvider 只能使用 openai_chat_completions 协议")
        self.config = config
        self._transport = transport or HttpxTransport(timeout_seconds=config.timeout_seconds)
        self._owns_transport = transport is None
        self._key_lookup = key_lookup or os.getenv

    async def submit(self, request: dict[str, Any]) -> ProviderSubmission:
        api_key = self._get_api_key()
        if api_key is None:
            raise ProviderTransportError(
                "当前供应商未配置 API Key",
                code="PROVIDER_NOT_CONFIGURED",
                retryable=False,
                fallback_allowed=False,
            )

        response = await self._transport.post_json(
            self.config.base_url,
            path=self._chat_completions_path(),
            api_key=api_key,
            payload=self._build_request_payload(request),
            timeout_seconds=self.config.timeout_seconds,
            provider_id=self.config.provider_id,
            model=self.config.model,
            idempotency_key=self._idempotency_key(request),
        )
        request_id = _response_id(response)
        document = self._parse_response(response, request_id=request_id)
        return ProviderSubmission(
            provider_request_id=request_id,
            mode="sync",
            status="succeeded",
            result=document.model_dump(mode="json", by_alias=True),
        )

    async def poll(self, submission: ProviderSubmission) -> ProviderPollResult:
        """Chat Completions 是同步协议，保留统一轮询接口。"""

        return ProviderPollResult(status=submission.status, result=submission.result)

    async def cancel(self, submission: ProviderSubmission) -> None:
        """Chat Completions 没有供应商原生异步任务，取消由本地任务引擎处理。"""

        return None

    async def health_check(self) -> ProviderHealth:
        if not self.config.enabled:
            return ProviderHealth(status=ProviderStatus.DISABLED)
        status = ProviderStatus.HEALTHY if self._get_api_key() is not None else ProviderStatus.UNHEALTHY
        return ProviderHealth(status=status)

    async def aclose(self) -> None:
        if self._owns_transport:
            await self._transport.aclose()

    async def __aenter__(self) -> "OpenAIChatCompletionsProvider":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.aclose()

    def _get_api_key(self) -> str | None:
        value = self._key_lookup(self.config.api_key_env)
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _chat_completions_path(self) -> str:
        # OpenAI 官方地址通常已包含 /v1；DeepSeek 官方地址按其协议直接使用根路径。
        parsed = urlsplit(self.config.base_url)
        base_path = parsed.path.rstrip("/")
        if base_path.endswith("/v1") or parsed.hostname == "api.deepseek.com":
            return "/chat/completions"
        return OPENAI_CHAT_COMPLETIONS_PATH

    def _idempotency_key(self, request: Mapping[str, Any]) -> str | None:
        for name in ("idempotency_key", "idempotencyKey"):
            value = request.get(name)
            if not isinstance(value, str):
                continue
            value = value.strip()
            if not value:
                continue
            if any(ord(char) < 32 for char in value):
                raise ProviderResponseError("幂等键格式无效")
            return value
        return None

    def _response_format(self) -> dict[str, Any]:
        # DeepSeek 和通用兼容服务使用 JSON mode；OpenAI 官方优先使用原生 JSON Schema。
        if urlsplit(self.config.base_url).hostname == "api.openai.com":
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "diagram_document",
                    "strict": True,
                    "schema": _openai_strict_schema(DiagramGenerationResult.model_json_schema()),
                },
            }
        return {"type": "json_object"}

    def _build_request_payload(self, request: Mapping[str, Any]) -> dict[str, Any]:
        prompt = request.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ProviderResponseError("流程描述不能为空")
        prompt = prompt.strip()
        if len(prompt) > 4000:
            raise ProviderResponseError("描述超过当前长度限制，请精简后重试", code="PROMPT_TOO_LONG")

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": build_generation_prompt(request)},
            ],
            "max_tokens": self.config.max_output_tokens,
            "response_format": self._response_format(),
            "stream": False,
        }
        # DeepSeek V4 默认开启高强度思考；结构化流程图的输出上限容易被
        # reasoning_tokens 耗尽，最终没有留下可解析的 JSON。仅对官方端点
        # 关闭思考，避免把该供应商专属参数发送给 OpenAI 或其他中转站。
        if urlsplit(self.config.base_url).hostname == "api.deepseek.com":
            payload["thinking"] = {"type": "enabled" if is_thinking_enabled(request) else "disabled"}
        return payload

    def _parse_response(self, response: Any, *, request_id: str | None) -> DiagramDocument:
        if not isinstance(response, Mapping):
            raise ProviderResponseError("供应商返回的消息格式无效", request_id=request_id)

        error = response.get("error")
        if isinstance(error, Mapping):
            error_type = str(error.get("type", "")).lower()
            if "content" in error_type or "safety" in error_type:
                raise ProviderResponseError("供应商拒绝生成该内容", request_id=request_id)
            raise ProviderResponseError("供应商未能完成请求", request_id=request_id)

        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ProviderResponseError("供应商未返回有效流程图结果", request_id=request_id)
        choice = choices[0]

        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise ProviderResponseError("供应商输出不完整", request_id=request_id)
        if isinstance(finish_reason, str) and finish_reason in _REFUSAL_FINISH_REASONS:
            raise ProviderResponseError("供应商拒绝生成该内容", request_id=request_id)

        message = choice.get("message")
        if not isinstance(message, Mapping):
            raise ProviderResponseError("供应商未返回有效流程图结果", request_id=request_id)
        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal.strip():
            raise ProviderResponseError("供应商拒绝生成该内容", request_id=request_id)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError("供应商未返回有效流程图结果", request_id=request_id)

        try:
            payload = _load_single_json_object(content, request_id=request_id)
        except ProviderResponseError:
            # 合法 JSON 中可以出现“无法”等业务文案，只有 JSON 不可解析时才识别纯文本拒绝。
            if _REFUSAL_TEXT_RE.search(content):
                raise ProviderResponseError("供应商拒绝生成该内容", request_id=request_id) from None
            raise
        return _validate_diagram_payload(payload, request_id=request_id)


def _response_id(response: Any) -> str | None:
    if not isinstance(response, Mapping):
        return None
    value = response.get("id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _load_single_json_object(text: str, *, request_id: str | None) -> dict[str, Any]:
    candidate = text.strip()
    match = _JSON_CODE_BLOCK_RE.fullmatch(candidate)
    if match:
        candidate = match.group(1).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        raise ProviderResponseError(
            "供应商返回的流程图 JSON 无法解析",
            code="DIAGRAM_SCHEMA_INVALID",
            request_id=request_id,
        ) from None
    if not isinstance(value, dict):
        raise ProviderResponseError(
            "供应商返回的流程图 JSON 必须是对象",
            code="DIAGRAM_SCHEMA_INVALID",
            request_id=request_id,
        )
    return value


def _validate_diagram_payload(payload: Mapping[str, Any], *, request_id: str | None) -> DiagramDocument:
    try:
        generation = DiagramGenerationResult.model_validate(dict(payload))
        return compile_generated_diagram_document(generation)
    except (ValidationError, ValueError):
        raise ProviderResponseError(
            "供应商返回的流程图不符合规范",
            code="DIAGRAM_SCHEMA_INVALID",
            request_id=request_id,
        ) from None


def _openai_strict_schema(value: Any) -> Any:
    """将 Pydantic Schema 收敛为 OpenAI strict JSON Schema 所需的对象规则。"""

    if isinstance(value, list):
        return [_openai_strict_schema(item) for item in value]
    if not isinstance(value, Mapping):
        return value

    result = {
        key: _openai_strict_schema(item)
        for key, item in value.items()
        if key != "default"
    }
    properties = result.get("properties")
    if isinstance(properties, Mapping):
        # OpenAI strict mode 要求每个对象字段进入 required；可选字段由其 JSON Schema 的 null 分支表示。
        result["required"] = list(properties)
        result["additionalProperties"] = False
    return result


__all__ = [
    "OPENAI_CHAT_COMPLETIONS_PATH",
    "OpenAIChatCompletionsProvider",
]
