from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.category.dtos import CategoryCreateSchema
from src.category.models import CategoryModel


class CategoryService:

    @staticmethod
    async def create(
        body: CategoryCreateSchema,
        db: AsyncSession,
    ) -> CategoryModel | None:
        existing = await db.scalar(
            select(CategoryModel).where(
                func.lower(CategoryModel.name) == body.name.lower()
            )
        )
        if existing is not None:
            return None

        category = CategoryModel(
            name=body.name.strip(),
            image=body.image,
            description=body.description,
        )
        db.add(category)
        await db.commit()
        await db.refresh(category)
        return category

    @staticmethod
    async def get_all(db: AsyncSession) -> list[CategoryModel]:
        rows = await db.scalars(select(CategoryModel))
        return list(rows.all())

    @staticmethod
    async def get_by_id_and_code(
        category_id: int,
        category_code: int,
        db: AsyncSession,
    ) -> CategoryModel:
        category = await db.scalar(
            select(CategoryModel).where(CategoryModel.id == category_id)
        )
        if category is None:
            raise HTTPException(status_code=404, detail="Category code not found")

        if category.category_code != category_code:
            raise HTTPException(
                status_code=400,
                detail="category code and id mismatch",
            )
        return category
