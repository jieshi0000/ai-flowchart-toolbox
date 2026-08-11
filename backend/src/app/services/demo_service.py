from uuid import UUID
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.demo_product import DemoProduct
from app.schemas.demo_product import DemoProductCreateReq, DemoProductUpdateReq, DemoProductVO, DemoProductPageReq
from app.schemas.common import PageResult


async def create_product(session: AsyncSession, req: DemoProductCreateReq) -> DemoProduct:
    product = DemoProduct(**req.model_dump())
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def get_product(session: AsyncSession, product_id: UUID) -> DemoProduct | None:
    result = await session.execute(select(DemoProduct).where(DemoProduct.id == product_id))
    return result.scalar_one_or_none()


async def update_product(session: AsyncSession, product: DemoProduct, req: DemoProductUpdateReq) -> DemoProduct:
    data = req.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(product, field, value)
    await session.commit()
    await session.refresh(product)
    return product


async def delete_product(session: AsyncSession, product_id: UUID) -> bool:
    result = await session.execute(sa_delete(DemoProduct).where(DemoProduct.id == product_id))
    await session.commit()
    return result.rowcount > 0


async def page_products(session: AsyncSession, page_req: DemoProductPageReq) -> PageResult:
    query = select(DemoProduct)
    count_query = select(func.count()).select_from(DemoProduct)

    if page_req.name:
        query = query.where(DemoProduct.name.contains(page_req.name))
        count_query = count_query.where(DemoProduct.name.contains(page_req.name))
    if page_req.status:
        query = query.where(DemoProduct.status == page_req.status)
        count_query = count_query.where(DemoProduct.status == page_req.status)
    if page_req.min_price is not None:
        query = query.where(DemoProduct.price >= page_req.min_price)
        count_query = count_query.where(DemoProduct.price >= page_req.min_price)
    if page_req.max_price is not None:
        query = query.where(DemoProduct.price <= page_req.max_price)
        count_query = count_query.where(DemoProduct.price <= page_req.max_price)

    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    query = query.offset(page_req.skip).limit(page_req.page_size)
    data_result = await session.execute(query)
    products = list(data_result.scalars().all())

    return PageResult.create(data=[to_vo(p) for p in products], total=total, page_req=page_req)


def to_vo(product: DemoProduct) -> DemoProductVO:
    return DemoProductVO.model_validate(product)
