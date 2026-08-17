async def test_page_default(client, reset_data):
    resp = await client.get("/api/demo/page")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["total"] == 15
    assert data["pages"] == 2
    assert data["pageNum"] == 1
    assert data["pageSize"] == 10
    assert len(data["records"]) == 10


async def test_page_second(client, reset_data):
    resp = await client.get("/api/demo/page?pageNum=2&pageSize=5")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["records"]) == 5
    assert data["pageNum"] == 2
    assert data["pages"] == 3


async def test_page_filter_name(client, reset_data):
    resp = await client.get("/api/demo/page?name=蓝牙")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] > 0
    for r in data["records"]:
        assert "蓝牙" in r["name"]


async def test_page_filter_status(client, reset_data):
    resp = await client.get("/api/demo/page?status=ACTIVE")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] > 0
    for r in data["records"]:
        assert r["status"] == "ACTIVE"


async def test_page_filter_price_range(client, reset_data):
    resp = await client.get("/api/demo/page?min_price=100&max_price=500")
    assert resp.status_code == 200
    data = resp.json()["data"]
    for r in data["records"]:
        assert 100 <= r["price"] <= 500


async def test_page_filter_combined(client, reset_data):
    resp = await client.get("/api/demo/page?name=蓝牙&status=ACTIVE")
    assert resp.status_code == 200
    data = resp.json()["data"]
    for r in data["records"]:
        assert "蓝牙" in r["name"]
        assert r["status"] == "ACTIVE"


async def test_page_no_results(client, reset_data):
    resp = await client.get("/api/demo/page?name=不存在的商品名称xyz")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["pages"] == 0
    assert data["records"] == []


async def test_page_response_structure(client, reset_data):
    resp = await client.get("/api/demo/page")
    data = resp.json()["data"]
    assert "pageNum" in data
    assert "pageSize" in data
    assert "pages" in data
    assert "total" in data
    assert "records" in data
