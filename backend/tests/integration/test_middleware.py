async def test_process_time_header(client, reset_data):
    resp = await client.get("/api/demo/page")
    assert "x-process-time" in resp.headers


async def test_cors_preflight(client, reset_data):
    resp = await client.options(
        "/api/demo/page",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


async def test_cors_get(client, reset_data):
    resp = await client.get("/api/demo/page", headers={"Origin": "http://example.com"})
    assert "access-control-allow-origin" in resp.headers


async def test_process_time_is_valid_float(client, reset_data):
    resp = await client.get("/api/demo/page")
    value = resp.headers["x-process-time"]
    duration = float(value)
    assert duration >= 0


async def test_cors_wildcard_origin(client, reset_data):
    resp = await client.get("/api/demo/page", headers={"Origin": "http://any-origin.com"})
    assert "access-control-allow-origin" in resp.headers


async def test_cors_allowed_methods(client, reset_data):
    resp = await client.options(
        "/api/demo/page",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-methods" in resp.headers
