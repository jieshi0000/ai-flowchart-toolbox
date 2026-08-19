import os
from functools import lru_cache
from typing import Annotated

from pydantic import BaseModel, BeforeValidator
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings

from app.core.crypto import decrypt

# 加载时自动解密 ENC(...)；明文配置不受影响
EncStr = Annotated[str, BeforeValidator(decrypt)]


def resolve_env_files() -> tuple[str, ...]:
    """配置层叠：.env → .env.{APP_ENV}（若设置了 APP_ENV）。

    进程环境变量由 pydantic-settings 以更高优先级覆盖文件值。
    """
    files: list[str] = [".env"]
    app_env = os.getenv("APP_ENV", "").strip()
    if app_env:
        files.append(f".env.{app_env}")
    return tuple(files)


class AppConfig(BaseModel):
    name: str = "flowchart-toolbox"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    json_camel_case: bool = True  # 默认 camelCase，与 Java 对齐；APP__JSON_CAMEL_CASE=false 关闭


class DatabaseConfig(BaseModel):
    url: EncStr = ""
    echo: bool = False
    pool_size: int = 20
    auto_migrate: bool = False


class LogConfig(BaseModel):
    level: str = "INFO"
    dir: str = "logs/"
    types: str = "console"
    rotation: bool = True


class SsoConfig(BaseModel):
    enabled: bool = False
    issuer: str = ""
    client_id: str = ""
    client_secret: EncStr = ""
    redirect_uri: str = ""
    frontend_callback: str = "/#/sso-callback"


class AuthConfig(BaseModel):
    enabled: bool = True
    captcha_enabled: bool = False
    sso: SsoConfig = SsoConfig()


class RedisConfig(BaseModel):
    url: EncStr = "redis://localhost:6379/0"


class MinioConfig(BaseModel):
    endpoint: str = "localhost:9000"
    access_key: EncStr = "minioadmin"
    secret_key: EncStr = "minioadmin"
    secure: bool = False
    bucket: str = "flowchart-exports"


class CeleryConfig(BaseModel):
    broker_url: EncStr = ""
    result_backend: EncStr = ""
    task_default_queue: str = "flowchart"


class AiConfig(BaseModel):
    """AI Provider 的非敏感运行配置。

    实际 Provider 清单由服务端文件加载；默认指向未跟踪的本机文件，避免
    示例配置被误当成真实密钥配置。文件路径可通过 ``AI__PROVIDERS_FILE``
    覆盖。
    """

    providers_file: str = "config/providers.local.json"
    mock_enabled: bool = False

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
    )


class Settings(BaseSettings):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    log: LogConfig = LogConfig()
    auth: AuthConfig = AuthConfig()
    redis: RedisConfig = RedisConfig()
    minio: MinioConfig = MinioConfig()
    celery: CeleryConfig = CeleryConfig()
    ai: AiConfig = AiConfig()

    model_config = {
        "case_sensitive": False,
        "extra": "ignore",
        # 嵌套分隔符：环境变量 APP__DEBUG 对应 Settings.app.debug
        "env_nested_delimiter": "__",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(_env_file=resolve_env_files())


# 保留一个全大写别名，便于配置模块调用方按领域命名导入。
AIConfig = AiConfig
