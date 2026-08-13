from uuid import UUID

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseDBModel


class FlowchartQuotaLog(BaseDBModel):
    __tablename__ = "flowchart_quota_log"

    # 积分流水不可变，V5 不设置 updated_at。
    updated_at = None

    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    balance_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
