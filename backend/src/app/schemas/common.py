import time
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel, Field
from math import ceil

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    code: int = Field(default=200)
    data: Optional[T] = Field(default=None)
    message: Optional[str] = Field(default=None)
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))

    @classmethod
    def success(cls, data: T = None, message: str = "操作成功") -> "Result[T]":
        return cls(code=200, data=data, message=message)

    @classmethod
    def error(cls, code: int = 500, message: str = "操作失败") -> "Result":
        return cls(code=code, message=message)


class PageReq(BaseModel):
    page_num: int = Field(default=1, ge=1, alias="pageNum")
    page_size: int = Field(default=10, ge=1, le=100, alias="pageSize")
    order_by: Optional[str] = Field(default=None, alias="orderBy")
    sort: Optional[str] = Field(default=None, alias="sort", pattern="^(asc|desc)$")

    model_config = {"populate_by_name": True}

    @property
    def skip(self) -> int:
        return (self.page_num - 1) * self.page_size


class PageResult(BaseModel, Generic[T]):
    page_num: int = Field(alias="pageNum")
    page_size: int = Field(alias="pageSize")
    pages: int = Field(alias="pages")
    total: int = Field(alias="total")
    records: list[T] = Field(default_factory=list, alias="records")

    model_config = {"populate_by_name": True}

    @classmethod
    def create(cls, data: list, total: int, page_req: "PageReq") -> "PageResult":
        pages = ceil(total / page_req.page_size) if total > 0 else 0
        return cls(
            page_num=page_req.page_num,
            page_size=page_req.page_size,
            pages=pages,
            total=total,
            records=data,
        )
