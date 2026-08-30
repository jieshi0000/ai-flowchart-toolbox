import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.demo_api import router as demo_router
from app.exceptions.handlers import register_exception_handlers
from app.middleware.logging import LoggingMiddleware
from app.middleware.cors import add_cors


@pytest.fixture
async def camel_client():
    camel_app = FastAPI(response_model_by_alias=True)
    register_exception_handlers(camel_app)
    camel_app.add_middleware(LoggingMiddleware)
    add_cors(camel_app)
    camel_app.include_router(demo_router, prefix="/api")
    for route in camel_app.routes:
        if isinstance(route, APIRoute):
            route.response_model_by_alias = True
    transport = ASGITransport(app=camel_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_camel_case_create_response(camel_client, reset_data):
    resp = await camel_client.post(
        "/api/demo/create",
        json={"name": "CamelCase商品", "price": 88.8},
    )
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert "isActive" in data
    assert "createdAt" in data
    assert "updatedAt" in data
    assert "viewCount" in data


async def test_camel_case_page_response(camel_client, reset_data):
    resp = await camel_client.get("/api/demo/page")
    body = resp.json()
    data = body["data"]
    assert "pageNum" in data
    assert "pageSize" in data
    assert "records" in data
    if data["records"]:
        record = data["records"][0]
        assert "isActive" in record
        assert "createdAt" in record


async def test_default_response_uses_camel_case(client, reset_data):
    """全局默认 APP__JSON_CAMEL_CASE=true，真实进程响应应为 camelCase。"""
    resp = await client.post(
        "/api/demo/create",
        json={"name": "DefaultCamel商品", "price": 66.6},
    )
    data = resp.json()["data"]
    assert "isActive" in data
    assert "createdAt" in data
    assert "viewCount" in data
    assert "is_active" not in data
