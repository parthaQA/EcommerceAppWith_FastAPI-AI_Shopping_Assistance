import csv
import json
from io import StringIO

from elasticsearch import AsyncElasticsearch
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.category.models import CategoryModel
from src.customers.models import CustomerModel
from src.products.dtos import ProductResponseSchema
from src.products.models import ProductModel
from src.utils.auth import AuthUser
from src.utils.es_client import ESClient, PRODUCT_INDEX
from src.utils.rabbitmq import RabbitMQ
from src.utils.redis import redis_client
from src.utils.settings import settings


class ProductController:

    @staticmethod
    async def add_product_by_category_id(
        category_id,
        body,
        db: AsyncSession,
        es: AsyncElasticsearch,
    ):
        result = await db.execute(
            select(CategoryModel).where(CategoryModel.id == category_id)
        )
        category = result.scalars().first()
        if not category:
            raise HTTPException(status_code=400, detail="Category does not exist")

        result = await db.execute(
            select(ProductModel).where(
                ProductModel.product_name == body.product_name,
                ProductModel.category_id == category_id,
            )
        )
        prod_name = result.scalars().first()

        if body.product_price <= 0 or body.product_quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity or price cannot be zero",
            )

        if prod_name:
            raise HTTPException(status_code=400, detail="Product already exists")

        product = ProductModel(
            product_name=body.product_name,
            product_price=body.product_price,
            product_quantity=body.product_quantity,
            product_description=body.product_description,
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
        return ProductResponseSchema(
            product_id=product.product_id,
            product_name=product.product_name,
        )

    @staticmethod
    async def add_bulk_products_by_csv(category_id: int, file, db: AsyncSession):
        result = await db.execute(
            select(CategoryModel).where(CategoryModel.id == category_id)
        )
        category = result.scalars().first()

        if not category:
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

                product_description = row.get("product_description", "").strip()

                await RabbitMQ.publish(
                    {
                        "product_name": product_name,
                        "product_price": price,
                        "product_quantity": quantity,
                        "product_description": product_description,
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
            "success": True,
            "message": "Products queued successfully",
            "queued_count": success_count,
            "failed_count": len(errors),
            "errors": errors,
        }

    @staticmethod
    async def get_all_products(limit, db: AsyncSession):
        result = await db.execute(select(ProductModel).limit(limit))
        products_list = result.scalars().all()
        return {
            "Success": True,
            "data": products_list,
            "count": limit,
        }

    @staticmethod
    async def get_product_by_product_id(product_id, db: AsyncSession):
        cache_data = f"product:{product_id}"
        get_product_id = await redis_client.get(cache_data)
        if get_product_id:
            return json.loads(get_product_id)

        result = await db.execute(
            select(ProductModel).where(ProductModel.product_id == product_id)
        )
        get_by_product_id = result.scalars().first()

        if not get_by_product_id:
            raise HTTPException(status_code=404, detail="Product does not exist")

        product_data = {
            "id": get_by_product_id.product_id,
            "product_name": get_by_product_id.product_name,
            "product_description": get_by_product_id.product_description,
            "product_price": get_by_product_id.product_price,
            "product_quantity": get_by_product_id.product_quantity,
        }
        await redis_client.set(cache_data, json.dumps(product_data), ex=60)
        return product_data

    @staticmethod
    async def update_a_product_by_id(
        product_id,
        body,
        db: AsyncSession,
        es: AsyncElasticsearch,
    ):
        result = await db.execute(
            select(ProductModel).where(ProductModel.product_id == product_id)
        )
        get_by_id = result.scalars().first()
        if not get_by_id:
            raise HTTPException(status_code=404, detail="Product does not exist")

        update_data = body.model_dump()
        for key, value in update_data.items():
            setattr(get_by_id, key, value)

        await db.commit()
        await db.refresh(get_by_id)
        await redis_client.delete(f"product:{product_id}")
        await ESClient.index_product(es, get_by_id)
        return get_by_id

    @staticmethod
    async def search_product_by_name(
        name: str,
        db: AsyncSession,
        es: AsyncElasticsearch,
        user: AuthUser,
    ):
        """Return products matching the search term via Elasticsearch."""
        result = await db.execute(
            select(CustomerModel).where(CustomerModel.id == user.customer_id)
        )
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail="Customer not found")

        es_result = await es.search(
            index=PRODUCT_INDEX,
            query={
                "match": {
                    "product_name": {
                        "query": name,
                        "fuzziness": "AUTO",
                    }
                }
            },
            size=50,
        )

        product_ids = [
            hit["_source"]["product_id"] for hit in es_result["hits"]["hits"]
        ]

        if not product_ids:
            return {
                "success": True,
                "data": [],
                "message": f"Found 0 products matching '{name}'",
            }

        result = await db.execute(
            select(ProductModel).where(ProductModel.product_id.in_(product_ids))
        )
        products_by_id = {p.product_id: p for p in result.scalars().all()}
        search_results = [
            products_by_id[pid] for pid in product_ids if pid in products_by_id
        ]

        return {
            "success": True,
            "data": search_results,
            "message": f"Found {len(search_results)} products matching '{name}'",
        }
