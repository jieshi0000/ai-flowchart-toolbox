import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.redis import get_redis
from app.schemas.user import HealthDataVO, ServiceHealth

_APP_START = datetime.now(timezone.utc)


def _format_uptime(start: datetime) -> str:
    delta = datetime.now(timezone.utc) - start
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


async def _check_postgres() -> ServiceHealth:
    start = time.perf_counter()
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = int((time.perf_counter() - start) * 1000)
        return ServiceHealth(status="connected", latencyMs=latency)
    except Exception:
        return ServiceHealth(status="error", latencyMs=None)


async def _check_redis() -> ServiceHealth:
    start = time.perf_counter()
    try:
        redis = get_redis()
        await redis.ping()
        latency = int((time.perf_counter() - start) * 1000)
        return ServiceHealth(status="connected", latencyMs=latency)
    except Exception:
        return ServiceHealth(status="error", latencyMs=None)


async def _check_minio() -> ServiceHealth:
    settings = get_settings()
    minio = settings.minio
    if not minio.endpoint:
        return ServiceHealth(status="error", latencyMs=None)

    scheme = "https" if minio.secure else "http"
    url = f"{scheme}://{minio.endpoint}/minio/health/live"
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            latency = int((time.perf_counter() - start) * 1000)
            return ServiceHealth(status="connected", latencyMs=latency)
        return ServiceHealth(status="error", latencyMs=None)
    except Exception:
        return ServiceHealth(status="error", latencyMs=None)


async def get_health() -> HealthDataVO:
    postgres = await _check_postgres()
    redis = await _check_redis()
    minio = await _check_minio()
    services = [postgres, redis, minio]
    overall = "ok" if all(item.status == "connected" for item in services) else "degraded"
    return HealthDataVO(
        status=overall,
        postgres=postgres,
        redis=redis,
        minio=minio,
        uptime=_format_uptime(_APP_START),
    )
