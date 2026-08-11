from functools import lru_cache
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@lru_cache(maxsize=1)
def get_engine():
    from app.core.config import get_settings

    settings = get_settings()
    url = settings.database.url.replace("postgresql://", "postgresql+asyncpg://")
    return create_async_engine(
        url, echo=settings.database.echo, pool_size=settings.database.pool_size
    )


@lru_cache(maxsize=1)
def get_session_factory():
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
