from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.common import Result
from app.schemas.user import (
    CaptchaLoginReq,
    CaptchaVO,
    LoginReq,
    LoginRespVO,
    UserInfoVO,
)
from app.services import auth_service as svc
from app.services import captcha_service

router = APIRouter(prefix="/auth", tags=["认证管理"])


def _extract_token(authorization: str | None, request: Request) -> str | None:
    if hasattr(request.state, "auth_token"):
        return request.state.auth_token
    return svc.parse_bearer_token(authorization)


@router.get("/captcha", response_model=Result[CaptchaVO], summary="获取验证码")
async def get_captcha():
    captcha_key, captcha_image = await captcha_service.create_captcha()
    return Result.success(data=CaptchaVO(captchaKey=captcha_key, captchaImage=captcha_image))


@router.post("/login", response_model=Result[LoginRespVO], summary="密码登录")
async def login(req: LoginReq, session: AsyncSession = Depends(get_session)):
    return Result.success(data=await svc.login(session, req))


@router.post("/login-by-captcha", response_model=Result[LoginRespVO], summary="验证码登录")
async def login_by_captcha(req: CaptchaLoginReq, session: AsyncSession = Depends(get_session)):
    return Result.success(data=await svc.login_by_captcha(session, req))


@router.get("/sso/authorize", summary="SSO 授权跳转")
async def sso_authorize():
    url = svc.build_sso_authorize_url()
    return RedirectResponse(url=url, status_code=302)


@router.get("/sso/callback", summary="SSO 回调")
async def sso_callback(code: str | None = None, session: AsyncSession = Depends(get_session)):
    redirect_url = await svc.handle_sso_callback(session, code)
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post("/refresh", response_model=Result[LoginRespVO], summary="刷新 token")
async def refresh_token(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    token = _extract_token(authorization, request)
    return Result.success(data=await svc.refresh(token))


@router.post("/logout", response_model=Result[dict], summary="登出")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    token = _extract_token(authorization, request)
    await svc.logout(token)
    return Result.success(data={})


@router.get("/me", response_model=Result[UserInfoVO], summary="获取当前用户信息")
async def get_me(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    token = _extract_token(authorization, request)
    return Result.success(data=await svc.get_me(token))
