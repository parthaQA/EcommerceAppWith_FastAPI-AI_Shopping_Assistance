from elasticsearch import AsyncElasticsearch
from sqlalchemy.ext.asyncio import AsyncSession

from src.products.dtos import ProductResponseSchema, ProductSchema
from src.products.product_service import ProductService
from src.utils.auth import AuthUser


class ProductController:

    @staticmethod
    async def add_product_by_category_id(
        category_id,
        body: ProductSchema,
        db: AsyncSession,
        es: AsyncElasticsearch,
    ):
        product = await ProductService.add_by_category_id(category_id, body, db, es)
        return ProductResponseSchema(
            product_id=product.product_id,
            product_name=product.product_name,
        )

    @staticmethod
    async def add_bulk_products_by_csv(category_id: int, file, db: AsyncSession):
        result = await ProductService.add_bulk_by_csv(category_id, file, db)
        return {
            "success": True,
            "message": "Products queued successfully",
            **result,
        }

    @staticmethod
    async def get_all_products(limit, db: AsyncSession):
        products = await ProductService.get_all(limit, db)
        return {
            "Success": True,
            "data": products,
            "count": limit,
        }

    @staticmethod
    async def get_product_by_product_id(product_id, db: AsyncSession):
        return await ProductService.get_by_id(product_id, db)

    @staticmethod
    async def update_a_product_by_id(
        product_id,
        body: ProductSchema,
        db: AsyncSession,
        es: AsyncElasticsearch,
    ):
        return await ProductService.update_by_id(product_id, body, db, es)

    @staticmethod
    async def search_product_by_name(
        name: str,
        db: AsyncSession,
        es: AsyncElasticsearch,
        user: AuthUser,
    ):
        products = await ProductService.search_by_name(
            name,
            user.customer_id,
            db,
            es,
        )
        return {
            "success": True,
            "data": products,
            "message": f"Found {len(products)} products matching '{name}'",
        }
