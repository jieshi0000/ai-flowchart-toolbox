from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.base import CamelVO


class LoginReq(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)
    captcha_key: str | None = Field(default=None, alias="captchaKey")
    captcha_code: str | None = Field(default=None, alias="captchaCode")

    model_config = {"populate_by_name": True}


class CaptchaLoginReq(BaseModel):
    phone: str = Field(min_length=1, max_length=20)
    captcha: str = Field(min_length=1, max_length=10)
    captcha_key: str = Field(min_length=1, alias="captchaKey")

    model_config = {"populate_by_name": True}


class LoginRespVO(CamelVO):
    token: str
    user_id: UUID = Field(alias="userId")
    username: str | None = None
    nickname: str | None = None
    role: str


class CaptchaVO(CamelVO):
    captcha_key: str = Field(alias="captchaKey")
    captcha_image: str = Field(alias="captchaImage")


class UserInfoVO(CamelVO):
    user_id: UUID = Field(alias="userId")
    username: str | None = None
    nickname: str | None = None
    role: str


class AuthConfigVO(CamelVO):
    auth_enabled: bool = Field(alias="authEnabled")
    captcha_enabled: bool = Field(alias="captchaEnabled")
    sso_enabled: bool = Field(alias="ssoEnabled")


class ServiceHealth(CamelVO):
    status: str
    latency_ms: int | None = None


class HealthDataVO(CamelVO):
    status: str
    postgres: ServiceHealth
    redis: ServiceHealth
    minio: ServiceHealth
    uptime: str
