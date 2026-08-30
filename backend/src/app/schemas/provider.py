from enum import StrEnum
import re
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.schemas.base import CamelVO


class ProviderAdapter(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"


class ProviderProtocol(StrEnum):
    ANTHROPIC_MESSAGES = "anthropic_messages"
    OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"
    OPENAI_RESPONSES = "openai_responses"


class ProviderCapability(StrEnum):
    TEXT_GENERATION = "text_generation"
    STRUCTURED_OUTPUT = "structured_output"


class ProviderStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    RATE_LIMITED = "rate_limited"
    DISABLED = "disabled"


class ProviderConfig(CamelVO):
    """服务端供应商配置。

    该模型同时用于校验提交到仓库的 ``providers.example.json`` 和本机的
    ``providers.local.json``。其中 ``api_key_env`` 只保存环境变量名，绝不
    保存密钥值；公开响应使用下面的 ``ProviderPublicInfo``，不会直接序列化
    此模型。
    """

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    provider_id: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)
    adapter: ProviderAdapter
    protocol: ProviderProtocol
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=160)
    api_key_env: str = Field(min_length=1, max_length=120)
    capabilities: list[ProviderCapability] = Field(min_length=1)
    enabled: bool = True
    allow_manual_selection: bool = True
    priority: int = 0
    timeout_seconds: int = Field(default=60, gt=0, le=600)
    poll_interval_seconds: int = Field(default=3, gt=0, le=15)
    max_poll_interval_seconds: int = Field(default=15, gt=0, le=15)
    task_timeout_seconds: int = Field(default=600, gt=0, le=3600)
    max_output_tokens: int = Field(default=4096, gt=0, le=100_000)

    @field_validator("provider_id", "display_name", "model", "api_key_env")
    @classmethod
    def no_control_chars(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("供应商配置文本不能为空或包含控制字符")
        return value

    @field_validator("api_key_env")
    @classmethod
    def valid_api_key_env(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
            raise ValueError("apiKeyEnv 必须是大写环境变量名")
        return value

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("baseUrl 必须是 http 或 https 地址")
        if parsed.username or parsed.password:
            raise ValueError("baseUrl 不允许嵌入认证信息")
        if parsed.query or parsed.fragment:
            raise ValueError("baseUrl 不允许包含 query 或 fragment")
        return value

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value: list[ProviderCapability]) -> list[ProviderCapability]:
        if len(value) != len(set(value)):
            raise ValueError("capabilities 不能重复")
        return value

    @model_validator(mode="after")
    def display_matches_model(self) -> "ProviderConfig":
        if self.display_name != self.model:
            raise ValueError("displayName 必须与 model 一致")
        if self.max_poll_interval_seconds < self.poll_interval_seconds:
            raise ValueError("maxPollIntervalSeconds 不能小于 pollIntervalSeconds")
        if self.adapter is ProviderAdapter.ANTHROPIC and self.protocol is not ProviderProtocol.ANTHROPIC_MESSAGES:
            raise ValueError("anthropic adapter 只能使用 anthropic_messages 协议")
        if self.adapter is ProviderAdapter.OPENAI_COMPATIBLE and self.protocol is ProviderProtocol.ANTHROPIC_MESSAGES:
            raise ValueError("openai_compatible adapter 不能使用 anthropic_messages 协议")
        return self

    def to_public_info(self, *, status: ProviderStatus | None = None) -> "ProviderPublicInfo":
        """生成不含私有配置的公开视图。"""

        return ProviderPublicInfo(
            provider_id=self.provider_id,
            display_name=self.display_name,
            model=self.model,
            capabilities=self.capabilities,
            status=status or ProviderStatus.HEALTHY,
            allow_manual_selection=self.allow_manual_selection,
        )


class ProviderPublicInfo(CamelVO):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    provider_id: str
    display_name: str
    model: str
    capabilities: list[ProviderCapability]
    status: ProviderStatus = ProviderStatus.HEALTHY
    allow_manual_selection: bool = True


class ProviderHealth(CamelVO):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    status: ProviderStatus
    latency_ms: int | None = Field(default=None, ge=0)
