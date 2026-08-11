import uuid
from app.models.demo_product import DemoProduct
from app.models.base import BaseDBModel


class TestBaseDBModel:
    def test_is_abstract(self):
        assert BaseDBModel.__abstract__ is True


class TestDemoProductModel:
    def test_has_all_columns(self):
        columns = {c.name for c in DemoProduct.__table__.columns}
        expected = {
            "id", "name", "description", "price", "stock", "view_count",
            "is_active", "status", "publish_date", "category_id", "tags",
            "ratings", "attributes", "created_at", "updated_at", "deleted_at",
        }
        assert expected <= columns

    def test_id_is_uuid_type(self):
        col = DemoProduct.__table__.c["id"]
        assert col.type.python_type == uuid.UUID

    def test_created_at_has_server_default(self):
        col = DemoProduct.__table__.c["created_at"]
        assert col.server_default is not None

    def test_updated_at_has_onupdate(self):
        col = DemoProduct.__table__.c["updated_at"]
        assert col.onupdate is not None

    def test_tablename(self):
        assert DemoProduct.__tablename__ == "demo_product"
