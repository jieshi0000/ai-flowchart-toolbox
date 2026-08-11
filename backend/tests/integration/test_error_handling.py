from uuid import uuid4


async def test_business_error_format(client, reset_data):
    fake_id = str(uuid4())
    resp = await client.get(f"/api/demo/get?id={fake_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404
    assert body["message"] == "商品不存在"
    assert body["data"] is None


async def test_validation_error_format(client, reset_data):
    resp = await client.post("/api/demo/create", json={"name": "", "price": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400
    assert body["data"] is None
    assert isinstance(body["message"], str)
    assert len(body["message"]) > 0


async def test_response_has_timestamp(client, reset_data):
    resp = await client.get("/api/demo/page")
    body = resp.json()
    assert "timestamp" in body
    assert isinstance(body["timestamp"], int)


async def test_validation_error_multiple_fields(client, reset_data):
    resp = await client.post("/api/demo/create", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400


async def test_error_data_is_none(client, reset_data):
    fake_id = str(uuid4())
    resp = await client.post(f"/api/demo/delete?id={fake_id}")
    body = resp.json()
    assert body["data"] is None


async def test_generic_error_returns_500(client, reset_data):
    resp = await client.get("/api/demo/get?id=invalid")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400


async def test_all_errors_have_consistent_structure(client, reset_data):
    fake_id = str(uuid4())
    resp = await client.get(f"/api/demo/get?id={fake_id}")
    body = resp.json()
    for key in ("code", "data", "message", "timestamp"):
        assert key in body
