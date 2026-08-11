async def test_docs_accessible(client, reset_data):
    resp = await client.get("/docs")
    assert resp.status_code == 200


async def test_openapi_schema_accessible(client, reset_data):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "paths" in schema
    assert "/api/demo/create" in schema["paths"]


async def test_response_content_type_json(client, reset_data):
    resp = await client.get("/api/demo/page")
    assert "application/json" in resp.headers["content-type"]


async def test_success_response_structure(client, reset_data):
    resp = await client.get("/api/demo/page")
    body = resp.json()
    assert body["code"] == 200
    assert body["message"] is not None
    assert body["timestamp"] > 0
