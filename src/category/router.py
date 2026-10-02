from typing import Annotated, List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.category.controller import CategoryController
from src.category.dtos import (
    CategoryCreateSchema,
    CategoryResponseSchema,
    ResponseSchema,
)
from src.utils.db import get_db

category_routes = APIRouter(prefix="/category")

@category_routes.post(
    "/create",
    response_model=ResponseSchema[CategoryResponseSchema],
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    body: CategoryCreateSchema,
    db: AsyncSession = Depends(get_db),
):
    return await CategoryController.create_categories(body, db)


@category_routes.get(
    "/all",
    response_model=ResponseSchema[List[CategoryResponseSchema]],
    status_code=status.HTTP_200_OK,
)
async def all_categories(
    db: AsyncSession = Depends(get_db),
):
    return await CategoryController.get_all_categories(db)
