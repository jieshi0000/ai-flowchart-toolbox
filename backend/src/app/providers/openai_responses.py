"""OpenAI Responses 兼容适配器。

DeepSeek Responses、OpenAI Responses 和遵循同一协议的中转站都通过本模块
接入。请求按无状态 Responses 契约重新组装，模型输出只作为 JSON 候选，
最终仍经过 DiagramDocument 与 Mermaid 编译边界校验。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from app.providers.base import ModelProvider, ProviderPollResult, ProviderSubmission
from app.providers.openai_chat import (
    _REFUSAL_TEXT_RE,
    _SYSTEM_PROMPT,
    _load_single_json_object,
    _openai_strict_schema,
    _validate_diagram_payload,
)
from app.providers.transport import HttpxTransport, ProviderResponseError, ProviderTransportError
from app.schemas.diagram import DiagramDocument, DiagramGenerationResult
from app.schemas.provider import (
    ProviderAdapter,
    ProviderCapability,
    ProviderConfig,
    ProviderHealth,
    ProviderProtocol,
    ProviderStatus,
)


OPENAI_RESPONSES_PATH = "/v1/responses"


class OpenAIResponsesProvider(ModelProvider):
    """将统一 Provider 请求转换为 OpenAI Responses 请求。"""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: HttpxTransport | None = None,
        key_lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        if config.adapter is not ProviderAdapter.OPENAI_COMPATIBLE:
            raise ValueError("OpenAIResponsesProvider 只能使用 openai_compatible adapter 配置")
        if config.protocol is not ProviderProtocol.OPENAI_RESPONSES:
            raise ValueError("OpenAIResponsesProvider 只能使用 openai_responses 协议")
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
            path=self._responses_path(),
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
        """Responses 是同步协议，保留统一轮询接口。"""

        return ProviderPollResult(status=submission.status, result=submission.result)

    async def cancel(self, submission: ProviderSubmission) -> None:
        """Responses 请求没有供应商原生异步任务，取消由本地任务引擎处理。"""

        return None

    async def health_check(self) -> ProviderHealth:
        if not self.config.enabled:
            return ProviderHealth(status=ProviderStatus.DISABLED)
        status = ProviderStatus.HEALTHY if self._get_api_key() is not None else ProviderStatus.UNHEALTHY
        return ProviderHealth(status=status)

    async def aclose(self) -> None:
        if self._owns_transport:
            await self._transport.aclose()

    async def __aenter__(self) -> "OpenAIResponsesProvider":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.aclose()

    def _get_api_key(self) -> str | None:
        value = self._key_lookup(self.config.api_key_env)
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _responses_path(self) -> str:
        # OpenAI 官方地址通常已包含 /v1；DeepSeek 官方地址按其协议直接使用根路径。
        parsed = urlsplit(self.config.base_url)
        base_path = parsed.path.rstrip("/")
        if base_path.endswith("/v1") or parsed.hostname == "api.deepseek.com":
            return "/responses"
        return OPENAI_RESPONSES_PATH

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

    def _supports_structured_output(self) -> bool:
        return ProviderCapability.STRUCTURED_OUTPUT in self.config.capabilities

    def _response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "name": "diagram_document",
            "strict": True,
            "schema": _openai_strict_schema(DiagramGenerationResult.model_json_schema()),
        }

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
        payload: dict[str, Any] = {
            "model": self.config.model,
            "instructions": _SYSTEM_PROMPT,
            "input": f"{prompt}{direction_note}",
            "max_output_tokens": self.config.max_output_tokens,
            "stream": False,
        }
        # 标准 Responses 服务使用原生 JSON Schema；未声明该能力的中转站
        # 依靠固定 instructions 和后端 Schema 校验兜底。
        if self._supports_structured_output():
            payload["text"] = {"format": self._response_format()}
        return payload

    def _parse_response(self, response: Any, *, request_id: str | None) -> DiagramDocument:
        if not isinstance(response, Mapping):
            raise ProviderResponseError("供应商返回的消息格式无效", request_id=request_id)

        error = response.get("error")
        if isinstance(error, Mapping):
            error_type = str(error.get("type", error.get("code", ""))).lower()
            if "content" in error_type or "safety" in error_type or "refusal" in error_type:
                raise ProviderResponseError("供应商拒绝生成该内容", request_id=request_id)
            raise ProviderResponseError("供应商未能完成请求", request_id=request_id)

        status = response.get("status")
        incomplete_details = response.get("incomplete_details")
        incomplete_reason = (
            str(incomplete_details.get("reason", "")).lower()
            if isinstance(incomplete_details, Mapping)
            else ""
        )
        if status == "incomplete" or incomplete_reason:
            if "content" in incomplete_reason or "safety" in incomplete_reason:
                raise ProviderResponseError("供应商拒绝生成该内容", request_id=request_id)
            raise ProviderResponseError("供应商输出不完整", request_id=request_id)
        if status == "failed":
            raise ProviderResponseError("供应商未能完成请求", request_id=request_id)

        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return self._parse_text(output_text, request_id=request_id)

        texts, refusal = _extract_output_text(response.get("output"))
        if refusal:
            raise ProviderResponseError("供应商拒绝生成该内容", request_id=request_id)
        if not texts:
            raise ProviderResponseError("供应商未返回有效流程图结果", request_id=request_id)
        return self._parse_text("".join(texts), request_id=request_id)

    def _parse_text(self, text: str, *, request_id: str | None) -> DiagramDocument:
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


def _extract_output_text(output: Any) -> tuple[list[str], bool]:
    """从标准 Responses output items 提取文本，并识别 refusal 内容。"""

    if not isinstance(output, list):
        return [], False
    texts: list[str] = []
    refusal = False
    for item in output:
        if not isinstance(item, Mapping):
            continue
        item_type = item.get("type")
        if item_type == "refusal":
            refusal = True
            continue
        if item_type == "output_text":
            value = item.get("text")
            if isinstance(value, str) and value.strip():
                texts.append(value)
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            part_type = part.get("type")
            if part_type == "refusal":
                refusal = True
                continue
            if part_type not in {"output_text", "text"}:
                continue
            value = part.get("text")
            if isinstance(value, str) and value.strip():
                texts.append(value)
    return texts, refusal


__all__ = ["OPENAI_RESPONSES_PATH", "OpenAIResponsesProvider"]
