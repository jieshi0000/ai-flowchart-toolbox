import uuid
from datetime import datetime

from sqlalchemy import String, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseDBModel


class SysUser(BaseDBModel):
    __tablename__ = "sys_user"

    username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENABLED")
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
