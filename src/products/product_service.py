import csv
import json
from io import StringIO

from elasticsearch import AsyncElasticsearch
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.category.models import CategoryModel
from src.customers.models import CustomerModel
from src.products.dtos import ProductSchema
from src.products.models import ProductModel
from src.utils.es_client import ESClient, PRODUCT_INDEX
from src.utils.rabbitmq import RabbitMQ
from src.utils.redis import redis_client
from src.utils.settings import settings


class ProductService:

    @staticmethod
    async def search_by_name(
        name: str,
        customer_id: str,
        db: AsyncSession,
        es: AsyncElasticsearch,
    ) -> list[ProductModel]:
        customer = await db.scalar(
            select(CustomerModel.id).where(CustomerModel.id == customer_id)
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")

        es_result = await es.search(
            index=PRODUCT_INDEX,
            query={"match": {"product_name": {"query": name, "fuzziness": "AUTO"}}},
            size=50,
        )
        ids = [h["_source"]["product_id"] for h in es_result["hits"]["hits"]]
        if not ids:
            return []

        rows = await db.scalars(
            select(ProductModel).where(ProductModel.product_id.in_(ids))
        )
        by_id = {p.product_id: p for p in rows}
        return [by_id[i] for i in ids if i in by_id]

    @staticmethod
    async def add_by_category_id(
        category_id: int,
        body: ProductSchema,
        db: AsyncSession,
        es: AsyncElasticsearch,
    ) -> ProductModel:
        category = await db.scalar(
            select(CategoryModel).where(CategoryModel.id == category_id)
        )
        if category is None:
            raise HTTPException(status_code=400, detail="Category does not exist")

        existing = await db.scalar(
            select(ProductModel).where(
                ProductModel.product_name == body.product_name,
                ProductModel.category_id == category_id,
            )
        )
        if body.product_price <= 0 or body.product_quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity or price cannot be zero",
            )
        if existing is not None:
            raise HTTPException(status_code=400, detail="Product already exists")

        product = ProductModel(
            product_name=body.product_name,
            product_price=body.product_price,
            product_quantity=body.product_quantity,
            product_description=body.product_description,
            unit=body.unit,
            category_id=category.id,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)

        try:
            await ESClient.index_product(es, product)
        except Exception as exc:
            print(f"Elasticsearch index failed: {exc}")
            await db.delete(product)
            await db.commit()
            raise HTTPException(
                status_code=503,
                detail="Product could not be added to search",
            )
        return product

    @staticmethod
    async def add_bulk_by_csv(
        category_id: int,
        file: UploadFile,
        db: AsyncSession,
    ) -> dict:
        category = await db.scalar(
            select(CategoryModel).where(CategoryModel.id == category_id)
        )
        if category is None:
            raise HTTPException(status_code=400, detail="Category does not exist")

        filename = (file.filename or "").lower()
        content_type = (file.content_type or "").lower()
        if not filename.endswith(".csv") and content_type not in {
            "text/csv",
            "application/csv",
            "application/vnd.ms-excel",
        }:
            raise HTTPException(status_code=400, detail="File must be a CSV file")

        try:
            contents_bytes = await file.read(settings.CSV_MAX_BYTES + 1)
        except Exception:
            raise HTTPException(status_code=400, detail="Unable to read CSV file")

        if len(contents_bytes) > settings.CSV_MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"CSV file exceeds max size of {settings.CSV_MAX_BYTES} bytes",
            )

        try:
            contents = contents_bytes.decode("utf-8")
        except Exception:
            raise HTTPException(status_code=400, detail="Unable to read CSV file")

        csv_reader = csv.DictReader(StringIO(contents))
        errors = []
        success_count = 0

        for idx, row in enumerate(csv_reader, start=1):
            if idx > settings.CSV_MAX_ROWS:
                errors.append(
                    {
                        "row": idx,
                        "product_name": None,
                        "error": f"Row limit of {settings.CSV_MAX_ROWS} exceeded",
                    }
                )
                break

            try:
                product_name = row.get("product_name", "").strip()
                if not product_name:
                    raise ValueError("Product name is required")

                try:
                    price = float(row.get("product_price"))
                except (TypeError, ValueError):
                    raise ValueError("Invalid product price")

                try:
                    quantity = int(row.get("product_quantity"))
                except (TypeError, ValueError):
                    raise ValueError("Invalid product quantity")

                if price <= 0:
                    raise ValueError("Price cannot be 0 or negative")
                if quantity <= 0:
                    raise ValueError("Quantity cannot be 0 or negative")

                unit = row.get("unit", "").strip()
                if not unit:
                    raise ValueError("Unit is required")

                product_description = row.get("product_description", "").strip()

                await RabbitMQ.publish(
                    {
                        "product_name": product_name,
                        "product_price": price,
                        "product_quantity": quantity,
                        "product_description": product_description,
                        "unit": unit,
                        "category_id": category_id,
                    }
                )
                success_count += 1
            except Exception as e:
                errors.append(
                    {
                        "row": idx,
                        "product_name": row.get("product_name"),
                        "error": str(e),
                    }
                )

        return {
            "queued_count": success_count,
            "failed_count": len(errors),
            "errors": errors,
        }

    @staticmethod
    async def get_all(limit: int, db: AsyncSession) -> list[ProductModel]:
        rows = await db.scalars(select(ProductModel).limit(limit))
        return list(rows.all())

    @staticmethod
    async def get_by_id(product_id: int, db: AsyncSession) -> dict:
        cache_key = f"product:{product_id}"
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)

        product = await db.scalar(
            select(ProductModel).where(ProductModel.product_id == product_id)
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Product does not exist")

        product_data = {
            "id": product.product_id,
            "product_name": product.product_name,
            "product_description": product.product_description,
            "product_price": product.product_price,
            "product_quantity": product.product_quantity,
            "unit": product.unit,
        }
        await redis_client.set(cache_key, json.dumps(product_data), ex=60)
        return product_data

    @staticmethod
    async def update_by_id(
        product_id: int,
        body: ProductSchema,
        db: AsyncSession,
        es: AsyncElasticsearch,
    ) -> ProductModel:
        product = await db.scalar(
            select(ProductModel).where(ProductModel.product_id == product_id)
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Product does not exist")

        for key, value in body.model_dump().items():
            setattr(product, key, value)

        await db.commit()
        await db.refresh(product)
        await redis_client.delete(f"product:{product_id}")
        await ESClient.index_product(es, product)
        return product
