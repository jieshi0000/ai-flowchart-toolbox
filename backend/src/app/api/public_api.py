from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.common import Result
from app.schemas.user import AuthConfigVO, HealthDataVO
from app.services import health_service

router = APIRouter(prefix="/public", tags=["公开接口"])


@router.get("/config", response_model=Result[AuthConfigVO], summary="获取认证配置")
async def get_public_config():
    settings = get_settings()
    return Result.success(
        data=AuthConfigVO(
            authEnabled=settings.auth.enabled,
            captchaEnabled=settings.auth.captcha_enabled,
            ssoEnabled=settings.auth.sso.enabled,
        )
    )


@router.get("/health", response_model=Result[HealthDataVO], summary="健康检查")
async def get_health():
    return Result.success(data=await health_service.get_health())
