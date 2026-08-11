from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field
from app.schemas.base import CamelVO, DatetimeFmt, DateFmt


class DemoProductCreateReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="商品名称")
    description: Optional[str] = Field(None, description="商品描述")
    price: float = Field(..., gt=0, description="价格")
    stock: int = Field(0, ge=0, description="库存")
    is_active: bool = Field(True, description="是否上架")
    status: str = Field("DRAFT", max_length=20, description="状态")
    publish_date: Optional[date] = Field(None, description="发布日期")
    category_id: Optional[UUID] = Field(None, description="分类ID")
    tags: Optional[list[str]] = Field(None, description="标签列表")
    ratings: Optional[list[int]] = Field(None, description="评分列表")
    attributes: Optional[dict] = Field(None, description="扩展属性")


class DemoProductUpdateReq(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="商品名称")
    description: Optional[str] = Field(None, description="商品描述")
    price: Optional[float] = Field(None, gt=0, description="价格")
    stock: Optional[int] = Field(None, ge=0, description="库存")
    is_active: Optional[bool] = Field(None, description="是否上架")
    status: Optional[str] = Field(None, max_length=20, description="状态")
    publish_date: Optional[date] = Field(None, description="发布日期")
    category_id: Optional[UUID] = Field(None, description="分类ID")
    tags: Optional[list[str]] = Field(None, description="标签列表")
    ratings: Optional[list[int]] = Field(None, description="评分列表")
    attributes: Optional[dict] = Field(None, description="扩展属性")


class DemoProductVO(CamelVO):
    id: UUID
    name: str
    description: Optional[str] = None
    price: float
    stock: int
    view_count: int
    is_active: bool
    status: str
    publish_date: Optional[DateFmt] = None
    category_id: Optional[UUID] = None
    tags: Optional[list[str]] = None
    ratings: Optional[list[int]] = None
    attributes: Optional[dict] = None
    created_at: Optional[DatetimeFmt] = None
    updated_at: Optional[DatetimeFmt] = None


class DemoProductPageReq(BaseModel):
    page_num: int = Field(default=1, ge=1, alias="pageNum")
    page_size: int = Field(default=10, ge=1, le=100, alias="pageSize")
    name: Optional[str] = Field(None, description="商品名称（模糊查询）")
    status: Optional[str] = Field(None, description="状态")
    min_price: Optional[float] = Field(None, description="最低价格")
    max_price: Optional[float] = Field(None, description="最高价格")

    model_config = {"populate_by_name": True}

    @property
    def skip(self) -> int:
        return (self.page_num - 1) * self.page_size
