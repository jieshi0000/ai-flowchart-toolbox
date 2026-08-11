from functools import lru_cache

import redis.asyncio as redis

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis.url, decode_responses=True)
