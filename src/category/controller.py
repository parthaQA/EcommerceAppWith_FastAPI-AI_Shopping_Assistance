from typing import List

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.category.dtos import (
    CategoryCreateSchema,
    CategoryResponseSchema,
    ResponseSchema,
)
from src.category.models import CategoryModel


class CategoryController:

    @staticmethod
    async def create_categories(body: CategoryCreateSchema, db: AsyncSession):
        try:
            result = await db.execute(
                select(CategoryModel).where(
                    func.lower(CategoryModel.name) == body.name.lower()
                )
            )
            existing_category = result.scalars().first()

            if existing_category:
                return ResponseSchema(
                    success=False,
                    data=None,
                    message="Category already exists",
                )

            category = CategoryModel(
                name=body.name.strip(),
                image=body.image,
                description=body.description,
            )
            db.add(category)
            await db.commit()
            await db.refresh(category)

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
            result = await db.execute(select(CategoryModel))
            categories = result.scalars().all()

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
        result = await db.execute(
            select(CategoryModel).where(CategoryModel.id == id)
        )
        category_id = result.scalars().first()

        result = await db.execute(
            select(CategoryModel).where(CategoryModel.category_code == category_code)
        )
        cat_code = result.scalars().first()

        if not category_id:
            raise HTTPException(status_code=404, detail="Category code not found")

        if category_id.category_code != category_code:
            return ResponseSchema(
                success=False,
                data=None,
                message="category code and id mismatch",
            )

        return ResponseSchema(
            success=True,
            data=[category_id],
            message=(
                "Category retrieved successfully"
                if cat_code and category_id
                else "No categories found"
            ),
        )
