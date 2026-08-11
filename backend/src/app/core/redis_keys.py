"""Redis key 规范：与 Java RedisUtil 一致 — {appName}:{bizName}:{key}"""

from app.core.config import get_settings

DELIMITER = ":"


def format_key(biz_name: str, key: str) -> str:
    app_name = get_settings().app.name
    return f"{app_name}{DELIMITER}{biz_name}{DELIMITER}{key}"
