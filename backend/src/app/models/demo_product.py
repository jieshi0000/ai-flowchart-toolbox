from sqlalchemy import String, Numeric, Integer, BigInteger, Boolean, Date, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseDBModel


class DemoProduct(BaseDBModel):
    __tablename__ = "demo_product"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(16, 4), nullable=False, default=0)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    publish_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    category_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    tags: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    ratings: Mapped[list | None] = mapped_column(ARRAY(Integer), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[str | None] = mapped_column(TIMESTAMP, nullable=True)
