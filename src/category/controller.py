from sqlalchemy.ext.asyncio import AsyncSession

from src.category.category_service import CategoryService
from src.category.dtos import (
    CategoryCreateSchema,
    CategoryResponseSchema,
    ResponseSchema,
)


class CategoryController:

    @staticmethod
    async def create_categories(body: CategoryCreateSchema, db: AsyncSession):
        try:
            category = await CategoryService.create(body, db)
            if category is None:
                return ResponseSchema(
                    success=False,
                    data=None,
                    message="Category already exists",
                )
            return ResponseSchema(
                success=True,
                data=CategoryResponseSchema.model_validate(category),
                message="Category created successfully",
            )
        except Exception:
            await db.rollback()
            return ResponseSchema(
                success=False,
                data=None,
                message="Failed to create category",
            )

    @staticmethod
    async def get_all_categories(db: AsyncSession):
        try:
            categories = await CategoryService.get_all(db)
            return ResponseSchema(
                success=True,
                data=[CategoryResponseSchema.model_validate(c) for c in categories],
                message=(
                    "All categories retrieved successfully"
                    if categories
                    else "No categories found"
                ),
            )
        except Exception:
            return ResponseSchema(
                success=False,
                data=None,
                message="Failed to retrieve categories",
            )

    @staticmethod
    async def get_cateogry_by_id(id, category_code, db: AsyncSession):
        category = await CategoryService.get_by_id_and_code(id, category_code, db)
        return ResponseSchema(
            success=True,
            data=[category],
            message="Category retrieved successfully",
        )
