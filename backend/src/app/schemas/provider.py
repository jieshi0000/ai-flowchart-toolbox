from enum import StrEnum

from pydantic import Field, model_validator

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
    task_timeout_seconds: int = Field(default=600, gt=0, le=3600)
    max_output_tokens: int = Field(default=4096, gt=0, le=100_000)

    @model_validator(mode="after")
    def display_matches_model(self) -> "ProviderConfig":
        if self.display_name != self.model:
            raise ValueError("displayName 必须与 model 一致")
        return self


class ProviderPublicInfo(CamelVO):
    provider_id: str
    display_name: str
    model: str
    capabilities: list[ProviderCapability]
    status: ProviderStatus = ProviderStatus.HEALTHY
    allow_manual_selection: bool = True


class ProviderHealth(CamelVO):
    status: ProviderStatus
    latency_ms: int | None = Field(default=None, ge=0)
