from fastapi import Request

from app.core.config import get_settings
from app.exceptions.business import BusinessException


def current_flowchart_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if isinstance(user_id, str) and user_id.strip():
        return user_id

    # 测试和关闭认证的纯本地模式允许使用本地用户标识模拟登录态。
    if not get_settings().auth.enabled:
        local_user_id = request.headers.get("X-Flowchart-User-Id", "local-user").strip()
        if local_user_id and len(local_user_id) <= 64:
            return local_user_id

    raise BusinessException(code=401, message="未登录")
