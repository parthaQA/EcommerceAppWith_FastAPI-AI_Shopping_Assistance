import asyncio

from elasticsearch import AsyncElasticsearch
from src.products.models import ProductModel
from src.utils.db import Local_Session
from src.utils.es_client import PRODUCT_INDEX, ESClient
from sqlalchemy import select


class ESAddProduct:

    @staticmethod
    async def add_product_to_es(es: AsyncElasticsearch):
        await ESClient.create_index_if_not_exists(es)

        async with Local_Session() as db:
            result = await db.execute(select(ProductModel))
            products = result.scalars().all()

            for product in products:
                await ESClient.index_product(es, product)

        print(f"Indexed {len(products)} products")

    @staticmethod
    async def get_es_product(es: AsyncElasticsearch):
        response = await es.search(
            index=PRODUCT_INDEX,
            query={"match_all": {}},
        )

        print(f"Total products: {response['hits']['total']}")

        for hit in response["hits"]["hits"]:
            print(hit["_source"])


async def _run():
    from src.utils.es_client import close_elasticsearch, connect_elasticsearch

    es = await connect_elasticsearch()
    try:
        await ESAddProduct.add_product_to_es(es)
    finally:
        await close_elasticsearch()


if __name__ == "__main__":
    asyncio.run(_run())
