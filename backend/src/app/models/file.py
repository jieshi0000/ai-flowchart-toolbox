from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseDBModel


class FlowchartFile(BaseDBModel):
    __tablename__ = "flowchart_file"

    # 文件记录为到期后清理的不可变审计条目；V5 仅维护 created_at。
    # 显式移除基类的 updated_at，确保 ORM 与迁移表结构一致。
    updated_at = None

    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    file_role: Mapped[str] = mapped_column(String(40), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
