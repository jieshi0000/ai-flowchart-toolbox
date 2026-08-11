import time
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.exceptions.business import BusinessException


async def business_error_handler(request: Request, exc: BusinessException):
    return JSONResponse(
        status_code=200,
        content={"code": exc.code, "data": None, "message": exc.message, "timestamp": int(time.time() * 1000)},
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = "; ".join(f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in errors)
    return JSONResponse(
        status_code=200,
        content={"code": 400, "data": None, "message": msg, "timestamp": int(time.time() * 1000)},
    )


async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"code": 500, "data": None, "message": "系统异常", "timestamp": int(time.time() * 1000)},
    )


def register_exception_handlers(app):
    app.add_exception_handler(BusinessException, business_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)
