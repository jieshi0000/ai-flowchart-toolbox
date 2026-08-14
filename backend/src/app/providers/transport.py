"""供应商统一 HTTPX 传输层。

所有供应商适配器都通过本模块发送 HTTP 请求。传输层统一处理超时、网络
错误、状态码映射、请求 ID 和安全日志；上层适配器无需接触 httpx 的细节。
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
from loguru import logger as default_logger


_SENSITIVE_KEY_RE = re.compile(
    r"(?:api[_-]?key|authorization|token|secret|password|passwd|credential|base[_-]?url|private[_-]?key)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[^\s,;]+")

# 保留模块级名称，便于应用统一配置和测试替换日志接收器。
logger = default_logger


def redact_sensitive(value: Any, *, secrets: Sequence[str] = ()) -> Any:
    """递归移除日志中的密钥、认证头和完整 Base URL。"""

    secret_values = tuple(secret for secret in secrets if secret)
    if isinstance(value, Mapping):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_sensitive(item, secrets=secret_values)
        return result
    if isinstance(value, (list, tuple, set)):
        converted = [redact_sensitive(item, secrets=secret_values) for item in value]
        return type(value)(converted) if not isinstance(value, tuple) else tuple(converted)
    if isinstance(value, str):
        result = _BEARER_RE.sub(r"\1[REDACTED]", value)
        for secret in secret_values:
            result = result.replace(secret, "[REDACTED]")
        return result
    return value


class ProviderTransportError(RuntimeError):
    """统一传输错误。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PROVIDER_SUBMIT_FAILED",
        retryable: bool = False,
        fallback_allowed: bool = False,
        status_code: int | None = None,
        request_id: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.fallback_allowed = fallback_allowed
        self.status_code = status_code
        self.request_id = request_id
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class ProviderTimeoutError(ProviderTransportError):
    def __init__(self, *, request_id: str | None = None) -> None:
        super().__init__(
            "供应商请求超时",
            code="PROVIDER_TASK_TIMEOUT",
            retryable=True,
            # 读取超时的计费状态不明确，不能自动切换第二个供应商。
            fallback_allowed=False,
            request_id=request_id,
        )


class ProviderNetworkError(ProviderTransportError):
    def __init__(self, *, request_id: str | None = None) -> None:
        super().__init__(
            "供应商网络连接失败",
            code="PROVIDER_SUBMIT_FAILED",
            retryable=True,
            fallback_allowed=True,
            request_id=request_id,
        )


class ProviderHTTPError(ProviderTransportError):
    def __init__(
        self,
        status_code: int,
        *,
        request_id: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        if status_code in {401, 403}:
            code = "PROVIDER_AUTH_FAILED"
            message = "供应商认证失败"
            retryable = False
            fallback_allowed = False
        elif status_code == 429:
            code = "PROVIDER_RATE_LIMITED"
            message = "供应商当前受到限流"
            retryable = True
            fallback_allowed = True
        elif status_code >= 500:
            code = "PROVIDER_UNHEALTHY"
            message = "供应商服务暂时不可用"
            retryable = True
            fallback_allowed = True
        else:
            code = "PROVIDER_SUBMIT_FAILED"
            message = "供应商请求参数或内容不被接受"
            retryable = False
            fallback_allowed = False
        super().__init__(
            message,
            code=code,
            retryable=retryable,
            fallback_allowed=fallback_allowed,
            status_code=status_code,
            request_id=request_id,
            retry_after_seconds=retry_after_seconds,
        )


class ProviderResponseError(ProviderTransportError):
    def __init__(self, *, request_id: str | None = None) -> None:
        super().__init__(
            "供应商返回了无法解析的响应",
            code="PROVIDER_SUBMIT_FAILED",
            retryable=False,
            fallback_allowed=False,
            request_id=request_id,
        )


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    try:
        seconds = int(value.strip())
        return max(0, seconds)
    except (TypeError, ValueError):
        # HTTP-date 形式也受支持，但不把日期原文带入日志或错误。
        try:
            from email.utils import parsedate_to_datetime

            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max(0, int((target - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return None


class HttpxTransport:
    """可注入 MockTransport 的异步 HTTPX 客户端。"""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 60,
        timeout: float | httpx.Timeout | None = None,
        logger_: Any | None = None,
    ) -> None:
        if timeout is not None:
            timeout_seconds = timeout if isinstance(timeout, (int, float)) else timeout_seconds
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")
        self.default_timeout = timeout if isinstance(timeout, httpx.Timeout) else float(timeout_seconds)
        self._client = client or httpx.AsyncClient(transport=transport)
        self._owns_client = client is None
        self._logger = logger_ or logger

    @staticmethod
    def build_url(base_url: str, path: str = "") -> str:
        base = base_url.rstrip("/")
        suffix = path if path.startswith("/") else f"/{path}" if path else ""
        return f"{base}{suffix}"

    async def request(
        self,
        method: str,
        url: str | None = None,
        *,
        base_url: str | None = None,
        path: str = "",
        api_key: str | None = None,
        headers: Mapping[str, str] | None = None,
        json: Any = None,
        payload: Any = None,
        params: Mapping[str, Any] | None = None,
        timeout_seconds: float | httpx.Timeout | None = None,
        provider_id: str | None = None,
        model: str | None = None,
        idempotency_key: str | None = None,
    ) -> httpx.Response:
        if url is None:
            url = base_url
        elif base_url is not None:
            raise TypeError("url 与 base_url 只能传一个")
        if not url:
            raise ValueError("请求地址不能为空")
        if path:
            url = self.build_url(url, path)
        parsed = urlsplit(str(url))
        if parsed.username or parsed.password:
            raise ValueError("请求地址不允许嵌入认证信息")
        request_id = uuid.uuid4().hex
        request_headers = {"Accept": "application/json", "X-Request-ID": request_id}
        if json is None and payload is not None:
            json = payload
        if headers:
            request_headers.update({str(key): str(value) for key, value in headers.items()})
        # 认证头和幂等头由传输层掌管，防止适配器误把它们写入日志或 URL。
        for key in list(request_headers):
            if key.lower() == "authorization":
                del request_headers[key]
        if api_key:
            request_headers["Authorization"] = f"Bearer {api_key}"
        if idempotency_key:
            request_headers["Idempotency-Key"] = idempotency_key

        safe_path = parsed.path or "/"
        timeout_value = timeout_seconds if timeout_seconds is not None else self.default_timeout
        timeout_arg = timeout_value
        self._logger.info(
            "provider http request provider={} model={} method={} path={} requestId={}",
            provider_id or "-",
            model or "-",
            method.upper(),
            safe_path,
            request_id,
        )

        try:
            response = await self._client.request(
                method.upper(),
                str(url),
                headers=request_headers,
                json=json,
                params=params,
                timeout=timeout_arg,
            )
        except httpx.TimeoutException:
            self._logger.warning(
                "provider http timeout provider={} method={} path={} requestId={}",
                provider_id or "-",
                method.upper(),
                safe_path,
                request_id,
            )
            raise ProviderTimeoutError(request_id=request_id) from None
        except httpx.RequestError:
            self._logger.warning(
                "provider http network error provider={} method={} path={} requestId={}",
                provider_id or "-",
                method.upper(),
                safe_path,
                request_id,
            )
            raise ProviderNetworkError(request_id=request_id) from None

        if response.status_code >= 400:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            error = ProviderHTTPError(
                response.status_code,
                request_id=request_id,
                retry_after_seconds=retry_after,
            )
            self._logger.warning(
                "provider http status provider={} method={} path={} status={} requestId={} code={}",
                provider_id or "-",
                method.upper(),
                safe_path,
                response.status_code,
                request_id,
                error.code,
            )
            raise error

        self._logger.info(
            "provider http response provider={} method={} path={} status={} requestId={}",
            provider_id or "-",
            method.upper(),
            safe_path,
            response.status_code,
            request_id,
        )
        response.extensions["provider_request_id"] = request_id
        return response

    async def request_json(self, method: str, url: str | None = None, **kwargs: Any) -> Any:
        response = await self.request(method, url, **kwargs)
        try:
            return response.json()
        except (ValueError, TypeError):
            request_id = response.extensions.get("provider_request_id")
            self._logger.warning(
                "provider invalid json response requestId={}",
                request_id or "-",
            )
            raise ProviderResponseError(request_id=request_id) from None

    async def send(self, method: str, url: str | None = None, **kwargs: Any) -> httpx.Response:
        """``request`` 的语义别名，便于适配器表达发送动作。"""

        return await self.request(method, url, **kwargs)

    async def json_request(self, method: str, url: str | None = None, **kwargs: Any) -> Any:
        return await self.request_json(method, url, **kwargs)

    async def get_json(self, url: str | None = None, path: str = "", **kwargs: Any) -> Any:
        return await self.request_json("GET", url, path=path, **kwargs)

    async def post_json(self, url: str | None = None, path: str = "", **kwargs: Any) -> Any:
        return await self.request_json("POST", url, path=path, **kwargs)

    async def get(self, url: str | None = None, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str | None = None, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "HttpxTransport":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.aclose()


# 文档和后续适配器可使用更语义化的名称；保留同一实现。
UnifiedHttpxTransport = HttpxTransport
ProviderHttpTransport = HttpxTransport
ProviderTransport = HttpxTransport
ProviderTimeout = ProviderTimeoutError
ProviderNetworkException = ProviderNetworkError
ProviderHttpException = ProviderHTTPError


__all__ = [
    "HttpxTransport",
    "ProviderHTTPError",
    "ProviderNetworkError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderTransportError",
    "ProviderHttpTransport",
    "ProviderHttpException",
    "ProviderNetworkException",
    "ProviderTimeout",
    "ProviderTransport",
    "UnifiedHttpxTransport",
    "redact_sensitive",
]
