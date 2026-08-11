import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.services.auth_service import parse_bearer_token

PUBLIC_PREFIXES = ("/api/auth/", "/api/public/", "/auth/", "/public/")
PUBLIC_EXACT = ("/docs", "/openapi.json", "/redoc", "/api/docs", "/api/openapi.json", "/api/redoc")


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT or path.startswith("/docs/"):
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.auth.enabled:
            return await call_next(request)

        if request.method == "OPTIONS" or _is_public_path(request.url.path):
            return await call_next(request)

        token = parse_bearer_token(request.headers.get("Authorization"))
        if not token:
            return JSONResponse(
                status_code=200,
                content={
                    "code": 401,
                    "data": None,
                    "message": "未登录",
                    "timestamp": int(time.time() * 1000),
                },
            )

        from app.services.auth_service import get_session

        session_data = await get_session(token)
        if not session_data:
            return JSONResponse(
                status_code=200,
                content={
                    "code": 401,
                    "data": None,
                    "message": "登录已过期",
                    "timestamp": int(time.time() * 1000),
                },
            )

        request.state.auth_token = token
        request.state.user_id = session_data.get("userId")
        request.state.user_session = session_data
        return await call_next(request)
