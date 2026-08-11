from pydantic.alias_generators import to_camel


def test_to_camel_normal():
    assert to_camel("hello_world") == "helloWorld"


def test_to_camel_single_word():
    assert to_camel("x") == "x"


def test_to_camel_empty():
    assert to_camel("") == ""


def test_to_camel_no_underscore():
    assert to_camel("already") == "already"


def test_to_camel_multiple():
    assert to_camel("a_b_c") == "aBC"


def test_to_camel_is_active():
    assert to_camel("is_active") == "isActive"


def test_to_camel_view_count():
    assert to_camel("view_count") == "viewCount"


def test_to_camel_created_at():
    assert to_camel("created_at") == "createdAt"


def test_vo_camel_serialization():
    from app.schemas.demo_product import DemoProductVO
    from uuid import uuid4
    from datetime import datetime

    vo = DemoProductVO(
        id=uuid4(), name="test", price=10.0, stock=5,
        view_count=0, is_active=True, status="ACTIVE",
        created_at=datetime(2026, 1, 1, 12, 30, 45),
    )
    dumped = vo.model_dump(by_alias=True)
    assert "isActive" in dumped
    assert "viewCount" in dumped
    assert "createdAt" in dumped
    assert dumped["createdAt"] == "2026-01-01 12:30:45"
    assert "is_active" not in dumped


def test_vo_snake_serialization():
    from app.schemas.demo_product import DemoProductVO
    from uuid import uuid4

    vo = DemoProductVO(
        id=uuid4(), name="test", price=10.0, stock=5,
        view_count=0, is_active=True, status="ACTIVE",
    )
    dumped = vo.model_dump(by_alias=False)
    assert "is_active" in dumped
    assert "view_count" in dumped
    assert "isActive" not in dumped


def test_page_result_alias():
    from app.schemas.common import PageResult

    pr = PageResult(page_num=1, page_size=10, pages=2, total=15, records=[])
    dumped = pr.model_dump(by_alias=True)
    assert "pageNum" in dumped
    assert "pageSize" in dumped

    dumped_snake = pr.model_dump(by_alias=False)
    assert "page_num" in dumped_snake
    assert "page_size" in dumped_snake
