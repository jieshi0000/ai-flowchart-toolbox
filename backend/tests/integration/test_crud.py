from uuid import uuid4


async def _create_test_product(client):
    resp = await client.post(
        "/api/demo/create",
        json={
            "name": "测试商品",
            "description": "测试描述",
            "price": 99.99,
            "stock": 100,
            "is_active": True,
            "status": "ACTIVE",
            "tags": ["测试", "新品"],
            "ratings": [5, 4, 5],
            "attributes": {"color": "红色", "size": "L"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    return body["data"]


async def test_create_product(client, reset_data):
    resp = await client.post("/api/demo/create", json={"name": "创建测试商品", "price": 199.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["name"] == "创建测试商品"
    assert body["data"]["price"] == 199.0
    assert body["data"]["id"] is not None
    assert body["data"]["createdAt"] is not None
    assert body["data"]["updatedAt"] is not None


async def test_create_product_all_fields(client, reset_data):
    resp = await client.post(
        "/api/demo/create",
        json={
            "name": "完整商品",
            "description": "描述",
            "price": 299.0,
            "stock": 50,
            "is_active": True,
            "status": "ACTIVE",
            "tags": ["电子"],
            "ratings": [5, 4],
            "attributes": {"key": "value"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "完整商品"
    assert data["stock"] == 50
    assert data["tags"] == ["电子"]
    assert data["ratings"] == [5, 4]
    assert data["attributes"] == {"key": "value"}


async def test_get_product(client, reset_data):
    product = await _create_test_product(client)
    product_id = product["id"]
    resp = await client.get(f"/api/demo/get?id={product_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["id"] == product_id
    assert body["data"]["name"] == "测试商品"


async def test_get_product_not_found(client, reset_data):
    fake_id = str(uuid4())
    resp = await client.get(f"/api/demo/get?id={fake_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404
    assert body["message"] == "商品不存在"
    assert body["data"] is None


async def test_get_product_invalid_uuid(client, reset_data):
    resp = await client.get("/api/demo/get?id=not-a-uuid")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400


async def test_update_product_partial(client, reset_data):
    product = await _create_test_product(client)
    product_id = product["id"]
    resp = await client.post(f"/api/demo/update?id={product_id}", json={"name": "更新后名称"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["name"] == "更新后名称"
    assert body["data"]["price"] == product["price"]


async def test_update_product_full(client, reset_data):
    product = await _create_test_product(client)
    product_id = product["id"]
    resp = await client.post(
        f"/api/demo/update?id={product_id}",
        json={
            "name": "全量更新",
            "description": "新描述",
            "price": 199.0,
            "stock": 999,
            "is_active": False,
            "status": "INACTIVE",
            "tags": ["更新"],
            "ratings": [1, 2],
            "attributes": {"updated": True},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "全量更新"
    assert data["stock"] == 999
    assert data["isActive"] is False


async def test_update_product_not_found(client, reset_data):
    fake_id = str(uuid4())
    resp = await client.post(f"/api/demo/update?id={fake_id}", json={"name": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404


async def test_update_product_empty(client, reset_data):
    product = await _create_test_product(client)
    product_id = product["id"]
    resp = await client.post(f"/api/demo/update?id={product_id}", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["name"] == product["name"]


async def test_delete_product(client, reset_data):
    product = await _create_test_product(client)
    product_id = product["id"]
    resp = await client.post(f"/api/demo/delete?id={product_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200

    resp2 = await client.get(f"/api/demo/get?id={product_id}")
    assert resp2.json()["code"] == 404


async def test_delete_product_not_found(client, reset_data):
    fake_id = str(uuid4())
    resp = await client.post(f"/api/demo/delete?id={fake_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 404


async def test_create_missing_name(client, reset_data):
    resp = await client.post("/api/demo/create", json={"price": 10.0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400


async def test_create_missing_price(client, reset_data):
    resp = await client.post("/api/demo/create", json={"name": "test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400


async def test_create_negative_price(client, reset_data):
    resp = await client.post("/api/demo/create", json={"name": "test", "price": -1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400


async def test_create_negative_stock(client, reset_data):
    resp = await client.post("/api/demo/create", json={"name": "test", "price": 10.0, "stock": -1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400
