import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from loguru import logger


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(
            "Request",
            method=request.method,
            url=str(request.url),
            status=response.status_code,
            duration=f"{duration:.4f}s",
        )
        response.headers["X-Process-Time"] = str(duration)
        return response
