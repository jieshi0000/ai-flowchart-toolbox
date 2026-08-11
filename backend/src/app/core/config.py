import os
from functools import lru_cache
from typing import Annotated

from pydantic import BaseModel, BeforeValidator
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


class Settings(BaseSettings):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    log: LogConfig = LogConfig()
    auth: AuthConfig = AuthConfig()
    redis: RedisConfig = RedisConfig()
    minio: MinioConfig = MinioConfig()

    model_config = {
        "case_sensitive": False,
        "extra": "ignore",
        # 嵌套分隔符：环境变量 APP__DEBUG 对应 Settings.app.debug
        "env_nested_delimiter": "__",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(_env_file=resolve_env_files())
