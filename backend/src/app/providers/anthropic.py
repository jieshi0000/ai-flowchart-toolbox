"""Anthropic Messages API 适配器。

本模块只处理 Anthropic 原生协议。流程图 JSON 通过强制工具调用返回，
随后仍会交给项目的 Pydantic 和 Mermaid 编译边界校验。
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


ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_MESSAGES_PATH = "/v1/messages"
DIAGRAM_TOOL_NAME = "submit_diagram"

_SYSTEM_PROMPT = (
    "根据用户描述生成流程图。必须调用 submit_diagram 工具，并且只能在工具输入中"
    "提供符合 Schema 的流程图 JSON。你必须根据流程层级、分支和阅读顺序，在 TB（自上而下）与 LR（从左到右）"
    "之间选择 direction。mermaidSource 必须与 JSON 表达相同流程，第一行严格为 flowchart TB 或 flowchart LR；"
    "按 nodes 数组顺序使用 n0、n1 等别名，每个节点和连线单独一行，连线标签只能写成 -->|文本|；"
    "禁止 HTML、注释、初始化指令、click、style、class、link 或其他交互、样式和外部引用语法。"
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
_REFUSAL_STOP_REASONS = frozenset({"refusal", "content_filtered", "safety"})


class AnthropicMessagesProvider(ModelProvider):
    """将统一 Provider 请求转换为 Anthropic Messages 请求。"""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: HttpxTransport | None = None,
        key_lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        if config.adapter is not ProviderAdapter.ANTHROPIC:
            raise ValueError("AnthropicMessagesProvider 只能使用 anthropic adapter 配置")
        if config.protocol is not ProviderProtocol.ANTHROPIC_MESSAGES:
            raise ValueError("AnthropicMessagesProvider 只能使用 anthropic_messages 协议")
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
            path=self._messages_path(),
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
            },
            payload=self._build_request_payload(request),
            timeout_seconds=self.config.timeout_seconds,
            provider_id=self.config.provider_id,
            model=self.config.model,
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
        """Anthropic Messages 是同步协议，保留统一轮询接口。"""

        return ProviderPollResult(status=submission.status, result=submission.result)

    async def cancel(self, submission: ProviderSubmission) -> None:
        """Messages 请求没有供应商原生异步任务，取消由本地任务引擎处理。"""

        return None

    async def health_check(self) -> ProviderHealth:
        if not self.config.enabled:
            return ProviderHealth(status=ProviderStatus.DISABLED)
        status = ProviderStatus.HEALTHY if self._get_api_key() is not None else ProviderStatus.UNHEALTHY
        return ProviderHealth(status=status)

    async def aclose(self) -> None:
        if self._owns_transport:
            await self._transport.aclose()

    async def __aenter__(self) -> "AnthropicMessagesProvider":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.aclose()

    def _get_api_key(self) -> str | None:
        value = self._key_lookup(self.config.api_key_env)
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _messages_path(self) -> str:
        # 兼容 baseUrl 写成 https://api.anthropic.com 或 .../v1 两种形式。
        base_path = urlsplit(self.config.base_url).path.rstrip("/")
        return "/messages" if base_path.endswith("/v1") else ANTHROPIC_MESSAGES_PATH

    def _build_request_payload(self, request: Mapping[str, Any]) -> dict[str, Any]:
        prompt = request.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ProviderResponseError("流程描述不能为空")
        prompt = prompt.strip()
        if len(prompt) > 4000:
            raise ProviderResponseError("描述超过当前长度限制，请精简后重试", code="PROMPT_TOO_LONG")

        direction = request.get("direction")
        if direction == "AUTO":
            direction_note = "\n\n请自行判断最适合的流程图方向，并在 direction 和 mermaidSource 中使用同一个 TB 或 LR。"
        elif direction in {"TB", "LR"}:
            direction_note = f"\n\n流程图方向必须是 {direction}。"
        else:
            direction_note = ""
        return {
            "model": self.config.model,
            "max_tokens": self.config.max_output_tokens,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": f"{prompt}{direction_note}"}],
            "tools": [
                {
                    "name": DIAGRAM_TOOL_NAME,
                    "description": "提交经过约束的流程图 JSON。",
                    "input_schema": DiagramGenerationResult.model_json_schema(),
                }
            ],
            "tool_choice": {
                "type": "tool",
                "name": DIAGRAM_TOOL_NAME,
                "disable_parallel_tool_use": True,
            },
        }

    def _parse_response(self, response: Any, *, request_id: str | None) -> DiagramDocument:
        if not isinstance(response, Mapping):
            raise ProviderResponseError("供应商返回的消息格式无效", request_id=request_id)

        stop_reason = response.get("stop_reason")
        if isinstance(stop_reason, str) and stop_reason in _REFUSAL_STOP_REASONS:
            raise ProviderResponseError("供应商拒绝生成该内容", request_id=request_id)
        if stop_reason == "max_tokens":
            raise ProviderResponseError("供应商输出不完整", request_id=request_id)

        error = response.get("error")
        if isinstance(error, Mapping):
            error_type = str(error.get("type", "")).lower()
            if "content" in error_type or "safety" in error_type:
                raise ProviderResponseError("供应商拒绝生成该内容", request_id=request_id)
            raise ProviderResponseError("供应商未能完成请求", request_id=request_id)

        content = response.get("content")
        if not isinstance(content, list) or not content:
            raise ProviderResponseError("供应商未返回有效流程图结果", request_id=request_id)

        tool_inputs = [
            item.get("input")
            for item in content
            if isinstance(item, Mapping) and item.get("type") == "tool_use" and item.get("name") == DIAGRAM_TOOL_NAME
        ]
        if tool_inputs:
            if len(tool_inputs) != 1 or not isinstance(tool_inputs[0], Mapping):
                raise ProviderResponseError(
                    "供应商返回的流程图 JSON 无法解析",
                    code="DIAGRAM_SCHEMA_INVALID",
                    request_id=request_id,
                )
            return _validate_diagram_payload(tool_inputs[0], request_id=request_id)

        return self._parse_text_fallback(content, request_id=request_id)

    def _parse_text_fallback(self, content: list[Any], *, request_id: str | None) -> DiagramDocument:
        if len(content) != 1 or not isinstance(content[0], Mapping) or content[0].get("type") != "text":
            raise ProviderResponseError("供应商未返回有效流程图结果", request_id=request_id)
        text = content[0].get("text")
        if not isinstance(text, str) or not text.strip():
            raise ProviderResponseError("供应商未返回有效流程图结果", request_id=request_id)
        try:
            payload = _load_single_json_object(text, request_id=request_id)
        except ProviderResponseError:
            # 合法 JSON 中可以出现“无法”等业务文案，只有 JSON 不可解析时才识别纯文本拒绝。
            if _REFUSAL_TEXT_RE.search(text):
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


__all__ = [
    "ANTHROPIC_API_VERSION",
    "ANTHROPIC_MESSAGES_PATH",
    "DIAGRAM_TOOL_NAME",
    "AnthropicMessagesProvider",
]
