import asyncio
import json

import aio_pika
from sqlalchemy import select
from sqlalchemy.orm import configure_mappers

from src.category.models import CategoryModel
from src.products.models import ProductModel
from src.utils.db import Local_Session
from src.utils.es_client import ESClient, connect_elasticsearch, get_es_client
from src.utils.settings import settings

RABBITMQ_URL = settings.RABBITMQ_URL
configure_mappers()


async def process_message(message):
    async with message.process(requeue=True):
        payload = json.loads(message.body.decode())

        async with Local_Session() as db:
            try:
                result = await db.execute(
                    select(ProductModel).where(
                        ProductModel.product_name == payload["product_name"]
                    )
                )
                is_exist = result.scalars().first()

                if is_exist:
                    await ESClient.index_product(get_es_client(), is_exist)
                    return

                product = ProductModel(
                    product_name=payload["product_name"],
                    product_price=float(payload["product_price"]),
                    product_quantity=int(payload["product_quantity"]),
                    product_description=payload["product_description"],
                    unit=payload["unit"],
                    category_id=payload["category_id"],
                )

                print(f"Processing: {payload['product_name']}")
                db.add(product)
                await db.commit()
                await db.refresh(product)
                await ESClient.index_product(get_es_client(), product)
                print(f"Inserted: {payload['product_name']}")

            except Exception as e:
                await db.rollback()
                print(f"Error: {e}")
                raise


async def main():
    es = await connect_elasticsearch()
    await ESClient.create_index_if_not_exists(es)
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    queue = await channel.declare_queue("product_bulk_queue", durable=True)
    await queue.consume(process_message)
    print("Consumer Started")
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
