from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.provider import ProviderHealth


class ProviderSubmission:
    """供应商 submit 的协议无关结果。"""

    def __init__(
        self,
        provider_request_id: str | None = None,
        mode: str = "sync",
        status: str = "succeeded",
        result: dict[str, Any] | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        if mode not in {"sync", "async"}:
            raise ValueError("mode 只能是 sync 或 async")
        if status not in {"queued", "processing", "succeeded", "failed"}:
            raise ValueError("submit status 无效")
        if retry_after_seconds is not None and retry_after_seconds < 0:
            raise ValueError("retry_after_seconds 不能为负数")
        self.provider_request_id = provider_request_id
        self.mode = mode
        self.status = status
        self.result = result
        self.retry_after_seconds = retry_after_seconds


class ProviderPollResult:
    def __init__(
        self,
        status: str,
        result: dict[str, Any] | None = None,
        progress: int | None = None,
        retry_after_seconds: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if status not in {"queued", "processing", "succeeded", "failed", "canceled"}:
            raise ValueError("poll status 无效")
        if progress is not None and not 0 <= progress <= 100:
            raise ValueError("progress 必须在 0 到 100 之间")
        if retry_after_seconds is not None and retry_after_seconds < 0:
            raise ValueError("retry_after_seconds 不能为负数")
        self.status = status
        self.result = result
        self.progress = progress
        self.retry_after_seconds = retry_after_seconds
        self.error_code = error_code
        self.error_message = error_message


class ProviderResult:
    def __init__(
        self,
        success: bool,
        provider: str,
        model: str,
        request_id: str | None = None,
        data: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        duration_ms: int = 0,
        cost_amount: float | None = None,
    ) -> None:
        if duration_ms < 0:
            raise ValueError("duration_ms 不能为负数")
        if success and data is None:
            raise ValueError("成功的 ProviderResult 必须包含 data")
        if not success and not (error_code or error_message):
            raise ValueError("失败的 ProviderResult 必须包含错误信息")
        self.success = success
        self.provider = provider
        self.model = model
        self.request_id = request_id
        self.data = data
        self.error_code = error_code
        self.error_message = error_message
        self.duration_ms = duration_ms
        self.cost_amount = cost_amount


class ModelProvider(ABC):
    @abstractmethod
    async def submit(self, request: dict[str, Any]) -> ProviderSubmission:
        raise NotImplementedError

    @abstractmethod
    async def poll(self, submission: ProviderSubmission) -> ProviderPollResult:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, submission: ProviderSubmission) -> None:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        raise NotImplementedError
