from functools import lru_cache

import redis.asyncio as redis

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis.url, decode_responses=True)


async def close_redis() -> None:
    """关闭应用进程创建的 Redis client。"""

    if get_redis.cache_info().currsize == 0:
        return
    client = get_redis()
    try:
        await client.aclose()
    finally:
        get_redis.cache_clear()


__all__ = ["close_redis", "get_redis"]
