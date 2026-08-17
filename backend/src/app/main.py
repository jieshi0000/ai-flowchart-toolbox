import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute
from loguru import logger

from app.core.config import get_settings
from app.core.redis import close_redis
from app.core.logging import setup_logging
from app.middleware.logging import LoggingMiddleware
from app.middleware.cors import add_cors
from app.exceptions.handlers import register_exception_handlers
from app.api.demo_api import router as demo_router
from app.api.auth_api import router as auth_router
from app.api.public_api import router as public_router
from app.api.provider_api import router as provider_router
from app.api.task_api import router as task_router
from app.middleware.auth import AuthMiddleware
from app.providers.provider_registry import close_provider_registry

setup_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.database.url and settings.database.auto_migrate:
        logger.info("==================== 数据库迁移 ====================")
        try:
            from app.db.migrate import run_migrations

            executed = await asyncio.to_thread(run_migrations, settings.database.url)
            for fname in executed:
                logger.info("  ✅ {}", fname)
            if executed:
                logger.info("迁移完成：{} 个迁移已执行", len(executed))
            else:
                logger.info("数据库已是最新版本，无需迁移")
        except Exception as e:
            logger.error("迁移失败：{}", e)
            logger.error("服务启动中止，请先修复迁移文件或手动执行后重试")
            raise
        logger.info("==================================================")
    try:
        yield
    finally:
        await close_provider_registry()
        await close_redis()


app = FastAPI(title=settings.app.name, debug=settings.app.debug, lifespan=lifespan)

for router in (demo_router, auth_router, public_router, provider_router, task_router):
    for route in router.routes:
        if isinstance(route, APIRoute):
            route.response_model_by_alias = settings.app.json_camel_case

register_exception_handlers(app)
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)
add_cors(app)
app.include_router(demo_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(public_router, prefix="/api")
app.include_router(provider_router, prefix="/api")
app.include_router(task_router, prefix="/api")

logger.info("Application startup", name=settings.app.name, debug=settings.app.debug)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
    )
