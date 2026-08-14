"""Provider 清单的安全加载与校验。

Provider 配置是服务端运行时配置，不属于数据库或前端状态。文件中只保存
``apiKeyEnv`` 环境变量名，真实密钥由适配器在发起请求时按需读取。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import ValidationError
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.schemas.provider import ProviderConfig


class ProviderConfigurationError(ValueError):
    """供应商清单不可用。

    错误消息刻意不包含原始 JSON、环境变量值或完整 URL，避免配置错误被
    写入普通日志或 API 响应。
    """


class ProviderConfigFile(BaseModel):
    """对象形态配置文件的显式 Schema；数组形态仍由 Loader 支持。"""

    providers: list[ProviderConfig] = Field(default_factory=list)


def _backend_root() -> Path:
    # src/app/providers/config.py -> backend/
    return Path(__file__).resolve().parents[3]


def resolve_provider_config_path(
    path: str | Path | None = None,
    *,
    settings: Settings | None = None,
) -> Path:
    """解析 Provider 清单路径。

    相对路径优先按当前工作目录解析，便于测试传入临时文件；若当前目录
    没有该文件，再按 backend 根目录解析。不会读取或打印敏感文件内容。
    """

    configured = path
    if configured is None:
        configured = (settings or get_settings()).ai.providers_file
    candidate = Path(configured)
    if candidate.is_absolute():
        return candidate
    cwd_candidate = Path.cwd() / candidate
    if cwd_candidate.exists():
        return cwd_candidate
    return _backend_root() / candidate


def _extract_entries(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("providers"), list):
        return payload["providers"]
    raise ProviderConfigurationError("Provider 配置根节点必须是数组或包含 providers 数组的对象")


class ProviderConfigLoader:
    """加载并校验供应商配置清单。"""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        settings: Settings | None = None,
        allow_missing: bool = True,
    ) -> None:
        # 传入显式路径时不强制构造全局 Settings，便于离线单元测试且避免
        # 无关的数据库/中间件密文配置阻塞 Provider 清单校验。
        self.settings = settings if settings is not None else (get_settings() if path is None else None)
        self.path = resolve_provider_config_path(path, settings=self.settings)
        self.allow_missing = allow_missing

    def load(self) -> tuple[ProviderConfig, ...]:
        if not self.path.exists():
            if self.allow_missing:
                logger.warning("Provider 配置文件不存在，当前没有可用供应商")
                return ()
            raise ProviderConfigurationError("Provider 配置文件不存在")
        if not self.path.is_file():
            raise ProviderConfigurationError("Provider 配置路径不是文件")

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            entries = _extract_entries(payload)
        except ProviderConfigurationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError):
            # 不回显路径或原始异常文本；其中可能包含本机目录或配置片段。
            raise ProviderConfigurationError("Provider 配置文件无法读取") from None

        configs: list[ProviderConfig] = []
        seen_ids: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ProviderConfigurationError(f"Provider 配置第 {index + 1} 项必须是对象")
            try:
                config = ProviderConfig.model_validate(entry)
            except ValidationError as exc:
                # 只保留稳定的字段/规则摘要，不携带 input_value。
                fields = ", ".join(
                    str(error.get("loc", ())) for error in exc.errors(include_url=False, include_context=False)
                )
                suffix = f"（字段：{fields}）" if fields else ""
                raise ProviderConfigurationError(f"Provider 配置校验失败{suffix}") from None
            if config.provider_id in seen_ids:
                raise ProviderConfigurationError("Provider providerId 不能重复")
            seen_ids.add(config.provider_id)
            configs.append(config)
        return tuple(configs)


def load_provider_configs(
    path: str | Path | None = None,
    *,
    settings: Settings | None = None,
    allow_missing: bool = True,
) -> tuple[ProviderConfig, ...]:
    """函数式加载入口，供注册中心和测试复用。"""

    return ProviderConfigLoader(path, settings=settings, allow_missing=allow_missing).load()


__all__ = [
    "ProviderConfigurationError",
    "ProviderConfigFile",
    "ProviderConfigLoader",
    "load_provider_configs",
    "resolve_provider_config_path",
]
