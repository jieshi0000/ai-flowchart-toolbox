from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseDBModel


class FlowchartDocument(BaseDBModel):
    __tablename__ = "flowchart_document"

    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(4), nullable=False, default="TB")
    diagram_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    mermaid_source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_task_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
