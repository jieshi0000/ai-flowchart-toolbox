import pytest
from pydantic import ValidationError

from app.schemas.common import Result, PageReq, PageResult
from app.schemas.demo_product import (
    DemoProductCreateReq,
    DemoProductUpdateReq,
    DemoProductPageReq,
)


class TestResult:
    def test_success_with_data(self):
        r = Result.success(data={"key": "value"})
        assert r.code == 200
        assert r.data == {"key": "value"}
        assert r.message == "操作成功"
        assert r.model_dump(by_alias=True)["errorCode"] is None

    def test_success_without_data(self):
        r = Result.success()
        assert r.code == 200
        assert r.data is None

    def test_success_custom_message(self):
        r = Result.success(data=1, message="自定义消息")
        assert r.message == "自定义消息"

    def test_error_defaults(self):
        r = Result.error()
        assert r.code == 500
        assert r.message == "操作失败"
        assert r.data is None

    def test_error_custom(self):
        r = Result.error(code=404, message="未找到", error_code="RESOURCE_NOT_FOUND")
        assert r.code == 404
        assert r.message == "未找到"
        assert r.error_code == "RESOURCE_NOT_FOUND"

    def test_timestamp_ms_epoch(self):
        r = Result.success()
        assert isinstance(r.timestamp, int)
        assert r.timestamp > 0


class TestPageReq:
    def test_defaults(self):
        req = PageReq()
        assert req.page_num == 1
        assert req.page_size == 10

    def test_invalid_page_num_zero(self):
        with pytest.raises(ValidationError):
            PageReq(page_num=0)

    def test_invalid_page_num_negative(self):
        with pytest.raises(ValidationError):
            PageReq(page_num=-1)

    def test_invalid_page_size_too_large(self):
        with pytest.raises(ValidationError):
            PageReq(page_size=101)

    def test_invalid_page_size_zero(self):
        with pytest.raises(ValidationError):
            PageReq(page_size=0)

    def test_sort_asc(self):
        req = PageReq(sort="asc")
        assert req.sort == "asc"

    def test_sort_desc(self):
        req = PageReq(sort="desc")
        assert req.sort == "desc"

    def test_sort_case_sensitive(self):
        with pytest.raises(ValidationError):
            PageReq(sort="DESC")

    def test_sort_invalid_value(self):
        with pytest.raises(ValidationError):
            PageReq(sort="random")

    def test_skip_calculation(self):
        req = PageReq(page_num=2, page_size=10)
        assert req.skip == 10
        req2 = PageReq(page_num=3, page_size=5)
        assert req2.skip == 10

    def test_alias_support(self):
        req = PageReq(pageNum=2, pageSize=20)
        assert req.page_num == 2
        assert req.page_size == 20


class TestPageResult:
    def test_create_normal(self):
        req = PageReq(page_num=1, page_size=10)
        result = PageResult.create(data=[1, 2, 3], total=15, page_req=req)
        assert result.page_num == 1
        assert result.page_size == 10
        assert result.pages == 2
        assert result.total == 15
        assert len(result.records) == 3

    def test_create_zero_total(self):
        req = PageReq()
        result = PageResult.create(data=[], total=0, page_req=req)
        assert result.pages == 0
        assert result.total == 0
        assert result.records == []

    def test_create_exact_boundary(self):
        req = PageReq(page_size=5)
        result = PageResult.create(data=[1] * 5, total=15, page_req=req)
        assert result.pages == 3

    def test_create_remainder_page(self):
        req = PageReq(page_size=10)
        result = PageResult.create(data=[1] * 3, total=13, page_req=req)
        assert result.pages == 2


class TestDemoProductCreateReq:
    def test_valid(self):
        req = DemoProductCreateReq(name="测试商品", price=99.9)
        assert req.name == "测试商品"
        assert req.price == 99.9
        assert req.stock == 0
        assert req.is_active is True
        assert req.status == "DRAFT"

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            DemoProductCreateReq(name="", price=1.0)

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            DemoProductCreateReq(name="x" * 101, price=1.0)

    def test_price_zero(self):
        with pytest.raises(ValidationError):
            DemoProductCreateReq(name="test", price=0)

    def test_price_negative(self):
        with pytest.raises(ValidationError):
            DemoProductCreateReq(name="test", price=-1)

    def test_negative_stock(self):
        with pytest.raises(ValidationError):
            DemoProductCreateReq(name="test", price=1.0, stock=-1)

    def test_all_fields(self):
        from uuid import uuid4
        from datetime import date

        req = DemoProductCreateReq(
            name="全字段",
            description="描述",
            price=199.0,
            stock=50,
            is_active=False,
            status="ACTIVE",
            publish_date=date(2026, 6, 1),
            category_id=uuid4(),
            tags=["标签"],
            ratings=[5, 4],
            attributes={"key": "value"},
        )
        assert req.tags == ["标签"]
        assert req.ratings == [5, 4]
        assert req.attributes == {"key": "value"}


class TestDemoProductUpdateReq:
    def test_all_none_valid(self):
        req = DemoProductUpdateReq()
        data = req.model_dump(exclude_unset=True)
        assert data == {}

    def test_name_empty_rejected(self):
        with pytest.raises(ValidationError):
            DemoProductUpdateReq(name="")

    def test_partial_values(self):
        req = DemoProductUpdateReq(name="新名称", price=10.0)
        data = req.model_dump(exclude_unset=True)
        assert "name" in data
        assert "price" in data
        assert "description" not in data

    def test_price_zero_rejected(self):
        with pytest.raises(ValidationError):
            DemoProductUpdateReq(price=0)


class TestDemoProductPageReq:
    def test_defaults(self):
        req = DemoProductPageReq()
        assert req.page_num == 1
        assert req.page_size == 10
        assert req.skip == 0

    def test_alias_support(self):
        req = DemoProductPageReq(pageNum=3, pageSize=20)
        assert req.page_num == 3
        assert req.skip == 40

    def test_with_filters(self):
        req = DemoProductPageReq(name="蓝牙", status="ACTIVE", min_price=100, max_price=500)
        assert req.name == "蓝牙"
        assert req.status == "ACTIVE"
        assert req.min_price == 100
        assert req.max_price == 500
