from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.schemas.common import Result
from app.schemas.demo_product import DemoProductCreateReq, DemoProductUpdateReq, DemoProductVO, DemoProductPageReq
from app.exceptions.business import BusinessException
from app.services import demo_service as svc

router = APIRouter(prefix="/demo", tags=["商品管理"])


@router.post("/create", response_model=Result[DemoProductVO], summary="创建商品")
async def create_product(req: DemoProductCreateReq, session: AsyncSession = Depends(get_session)):
    product = await svc.create_product(session, req)
    return Result.success(data=svc.to_vo(product))


@router.get("/get", response_model=Result[DemoProductVO], summary="获取商品详情")
async def get_product(id: UUID, session: AsyncSession = Depends(get_session)):
    product = await svc.get_product(session, id)
    if not product:
        raise BusinessException(code=404, message="商品不存在")
    return Result.success(data=svc.to_vo(product))


@router.post("/update", response_model=Result[DemoProductVO], summary="更新商品")
async def update_product(id: UUID, req: DemoProductUpdateReq, session: AsyncSession = Depends(get_session)):
    product = await svc.get_product(session, id)
    if not product:
        raise BusinessException(code=404, message="商品不存在")
    product = await svc.update_product(session, product, req)
    return Result.success(data=svc.to_vo(product))


@router.post("/delete", response_model=Result[dict], summary="删除商品")
async def delete_product(id: UUID, session: AsyncSession = Depends(get_session)):
    success = await svc.delete_product(session, id)
    if not success:
        raise BusinessException(code=404, message="商品不存在")
    return Result.success(data={"id": str(id)})


@router.get("/page", response_model=Result, summary="分页查询商品")
async def page_products(
    page_num: int = Query(1, alias="pageNum"),
    page_size: int = Query(10, alias="pageSize"),
    name: str | None = None,
    status: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    session: AsyncSession = Depends(get_session),
):
    page_req = DemoProductPageReq(
        page_num=page_num, page_size=page_size, name=name, status=status, min_price=min_price, max_price=max_price
    )
    page_result = await svc.page_products(session, page_req)
    return Result.success(data=page_result)
