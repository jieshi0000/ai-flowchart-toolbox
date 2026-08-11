import json
import secrets
from uuid import UUID
from urllib.parse import urlencode

import bcrypt
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.core.redis_keys import format_key
from app.exceptions.business import BusinessException
from app.models.user import SysUser
from app.schemas.user import LoginReq, CaptchaLoginReq, LoginRespVO, UserInfoVO
from app.services import captcha_service

SESSION_BIZ = "session"
SESSION_TTL = 7 * 24 * 3600
SESSION_TOKEN_PREFIX = "sess_"


def parse_bearer_token(authorization: str | None) -> str | None:
    """从 Authorization: Bearer <sess_…> 取出完整会话 token（含 sess_ 前缀）。"""
    if not authorization:
        return None
    value = authorization.strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value or None


async def _save_session(user: SysUser) -> str:
    token = f"{SESSION_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    payload = {
        "userId": str(user.id),
        "username": user.username,
        "nickname": user.nickname,
        "role": user.role,
    }
    redis = get_redis()
    await redis.setex(format_key(SESSION_BIZ, token), SESSION_TTL, json.dumps(payload))
    return token


async def get_session(token: str) -> dict | None:
    redis = get_redis()
    data = await redis.get(format_key(SESSION_BIZ, token))
    if not data:
        return None
    return json.loads(data)


async def delete_session(token: str) -> None:
    redis = get_redis()
    await redis.delete(format_key(SESSION_BIZ, token))


async def refresh_session(token: str) -> bool:
    redis = get_redis()
    return bool(await redis.expire(format_key(SESSION_BIZ, token), SESSION_TTL))


def _to_login_resp(user: SysUser, token: str) -> LoginRespVO:
    return LoginRespVO(
        token=token,
        userId=user.id,
        username=user.username,
        nickname=user.nickname,
        role=user.role,
    )


def _to_user_info(session: dict) -> UserInfoVO:
    return UserInfoVO(
        userId=UUID(session["userId"]),
        username=session.get("username"),
        nickname=session.get("nickname"),
        role=session["role"],
    )


async def _get_active_user_by_username(session: AsyncSession, username: str) -> SysUser | None:
    result = await session.execute(
        select(SysUser).where(
            SysUser.username == username,
            SysUser.status == "ENABLED",
            SysUser.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _get_active_user_by_phone(session: AsyncSession, phone: str) -> SysUser | None:
    result = await session.execute(
        select(SysUser).where(
            SysUser.phone == phone,
            SysUser.status == "ENABLED",
            SysUser.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


def _verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


async def login(session: AsyncSession, req: LoginReq) -> LoginRespVO:
    settings = get_settings()
    if settings.auth.captcha_enabled:
        if not req.captcha_key or not req.captcha_code:
            raise BusinessException(code=400, message="验证码不能为空")
        if not await captcha_service.verify_captcha(req.captcha_key, req.captcha_code):
            raise BusinessException(code=400, message="验证码错误或已过期")
    user = await _get_active_user_by_username(session, req.username)
    if not user or not _verify_password(req.password, user.password_hash):
        raise BusinessException(code=401, message="用户名或密码错误")
    token = await _save_session(user)
    return _to_login_resp(user, token)


async def login_by_captcha(session: AsyncSession, req: CaptchaLoginReq) -> LoginRespVO:
    if not await captcha_service.verify_captcha(req.captcha_key, req.captcha):
        raise BusinessException(code=400, message="验证码错误或已过期")
    user = await _get_active_user_by_phone(session, req.phone)
    if not user:
        raise BusinessException(code=401, message="用户不存在")
    token = await _save_session(user)
    return _to_login_resp(user, token)


async def logout(token: str | None) -> None:
    if token:
        await delete_session(token)


async def refresh(token: str | None) -> LoginRespVO:
    if not token:
        raise BusinessException(code=401, message="未登录")
    session_data = await get_session(token)
    if not session_data:
        raise BusinessException(code=401, message="登录已过期")
    await refresh_session(token)
    return LoginRespVO(
        token=token,
        userId=UUID(session_data["userId"]),
        username=session_data.get("username"),
        nickname=session_data.get("nickname"),
        role=session_data["role"],
    )


async def get_me(token: str | None) -> UserInfoVO:
    if not token:
        raise BusinessException(code=401, message="未登录")
    session_data = await get_session(token)
    if not session_data:
        raise BusinessException(code=401, message="登录已过期")
    return _to_user_info(session_data)


def build_sso_authorize_url() -> str:
    settings = get_settings()
    sso = settings.auth.sso
    if not sso.enabled:
        raise BusinessException(code=400, message="SSO 未启用")
    if not sso.issuer or not sso.client_id or not sso.redirect_uri:
        raise BusinessException(code=500, message="SSO 配置不完整")
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": sso.client_id,
        "redirect_uri": sso.redirect_uri,
        "response_type": "code",
        "scope": "userid userinfo",
        "state": state,
    }
    issuer = sso.issuer.rstrip("/")
    return f"{issuer}/oauth2/authorize?{urlencode(params)}"


async def handle_sso_callback(session: AsyncSession, code: str | None) -> str:
    settings = get_settings()
    sso = settings.auth.sso
    if not sso.enabled:
        raise BusinessException(code=400, message="SSO 未启用")
    if not code:
        raise BusinessException(code=400, message="缺少授权码")
    if not sso.issuer or not sso.client_id or not sso.client_secret or not sso.redirect_uri:
        raise BusinessException(code=500, message="SSO 配置不完整")

    issuer = sso.issuer.rstrip("/")
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            f"{issuer}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": sso.client_id,
                "client_secret": sso.client_secret,
                "redirect_uri": sso.redirect_uri,
            },
        )
        if token_resp.status_code != 200:
            raise BusinessException(code=401, message="SSO token 交换失败")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise BusinessException(code=401, message="SSO 未返回 access_token")

        userinfo_resp = await client.get(
            f"{issuer}/oauth2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            raise BusinessException(code=401, message="SSO 用户信息获取失败")
        userinfo = userinfo_resp.json()

    username = userinfo.get("username") or userinfo.get("sub") or userinfo.get("userid")
    if not username:
        raise BusinessException(code=401, message="SSO 用户信息不完整")

    user = await _get_active_user_by_username(session, str(username))
    if not user:
        import uuid_utils

        user = SysUser(
            id=uuid_utils.uuid7(),
            username=str(username),
            nickname=userinfo.get("nickname") or str(username),
            role=userinfo.get("role") or "user",
            status="ENABLED",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = await _save_session(user)
    callback = sso.frontend_callback or "/#/sso-callback"
    separator = "&" if "?" in callback else "?"
    return f"{callback}{separator}token={token}"
