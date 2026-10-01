from typing import Annotated

from elasticsearch import AsyncElasticsearch
from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.products.controller import ProductController
from src.products.dtos import ProductResponseSchema, ProductSchema
from src.utils.auth import AuthUser, get_current_user
from src.utils.db import get_db
from src.utils.es_client import get_es
from src.utils.settings import settings

product_routes = APIRouter(prefix="/products")

@product_routes.post(
    "/{category_id}/add",
    response_model=ProductResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def add_product_by_category_id(
    category_id: int,
    body: ProductSchema,
    db: AsyncSession = Depends(get_db),
    es: AsyncElasticsearch = Depends(get_es),
):
    return await ProductController.add_product_by_category_id(
        category_id=category_id,
        body=body,
        db=db,
        es=es,
    )

@product_routes.post("/{category_id}/bulk-add", status_code=status.HTTP_201_CREATED)
async def add_product_in_bulk(
    category_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    return await ProductController.add_bulk_products_by_csv(
        category_id=category_id,
        file=file,
        db=db,
    )

@product_routes.get("/search/{name}", status_code=status.HTTP_200_OK)
async def search_product(
    name: str,
    es: AsyncElasticsearch = Depends(get_es),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await ProductController.search_product_by_name(
        name=name,
        db=db,
        es=es,
        user=user,
    )

@product_routes.get("/all", status_code=status.HTTP_200_OK)
async def get_all_products(
    limit: Annotated[int, Query(ge=1, le=settings.PRODUCT_LIST_MAX_LIMIT)] = 20,
    db: AsyncSession = Depends(get_db),
):
    return await ProductController.get_all_products(limit, db)

@product_routes.get("/{product_id}", status_code=status.HTTP_200_OK)
async def get_product_by_product_id(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await ProductController.get_product_by_product_id(product_id, db)

@product_routes.put("/{product_id}", status_code=status.HTTP_200_OK)
async def update_a_product_by_id(
    product_id: int,
    body: ProductSchema,
    db: AsyncSession = Depends(get_db),
    es: AsyncElasticsearch = Depends(get_es),
):
    return await ProductController.update_a_product_by_id(
        product_id,
        body,
        db,
        es,
    )
