from elasticsearch import AsyncElasticsearch
from fastapi import Request

from src.utils.settings import settings

PRODUCT_INDEX = "products"

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "product_id": {"type": "integer"},
            "product_name": {"type": "text"},
            "product_price": {"type": "float"},
            "product_quantity": {"type": "integer"},
        }
    }
}

_es: AsyncElasticsearch | None = None


async def connect_elasticsearch() -> AsyncElasticsearch:
    global _es
    if _es is None:
        _es = AsyncElasticsearch(settings.ELASTICSEARCH_URL)
    return _es


def get_es_client() -> AsyncElasticsearch:
    global _es
    if _es is None:
        _es = AsyncElasticsearch(settings.ELASTICSEARCH_URL)
    return _es


async def close_elasticsearch() -> None:
    global _es
    if _es is not None:
        await _es.close()
        _es = None


async def get_es(request: Request) -> AsyncElasticsearch:
    es = getattr(request.app.state, "es", None)
    if es is None:
        es = await connect_elasticsearch()
        request.app.state.es = es
    return es


class ESClient:

    @staticmethod
    async def create_index_if_not_exists(es: AsyncElasticsearch):
        exists = await es.indices.exists(index=PRODUCT_INDEX)
        if not exists:
            try:
                await es.indices.create(
                    index=PRODUCT_INDEX,
                    mappings=INDEX_MAPPING["mappings"],
                )
            except Exception as e:
                print("ES error detail:", getattr(e, "info", str(e)))
                raise

    @staticmethod
    async def index_product(es: AsyncElasticsearch, product) -> None:
        await ESClient.create_index_if_not_exists(es)
        await es.index(
            index=PRODUCT_INDEX,
            id=str(product.product_id),
            document={
                "product_id": product.product_id,
                "product_name": product.product_name,
                "product_price": product.product_price,
                "product_quantity": product.product_quantity,
            },
            refresh="wait_for",
        )
