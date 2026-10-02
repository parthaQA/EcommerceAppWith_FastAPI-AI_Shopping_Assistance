from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.cart.router import cart_routes
from src.category.router import category_routes
from src.customers.router import customer_routes
from src.order.controller import auto_accept_pending_orders
from src.order.router import order_routes
from src.products.router import product_routes
from src.utils.db import BASE, engine
from src.utils.es_client import close_elasticsearch, connect_elasticsearch
from src.utils.rabbitmq import RabbitMQ
from src.utils.redis import redis_client
from src.utils.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting FastAPI application...")

    async with engine.begin() as conn:
        await conn.run_sync(BASE.metadata.create_all)

    try:
        await redis_client.ping()
        print("Redis connected successfully")
    except Exception as e:
        print(f"Redis connection failed: {e}")
        raise

    try:
        await RabbitMQ.connect()
        print("RabbitMQ connected successfully")
    except Exception as e:
        print(f"RabbitMQ connection failed: {e}")

    try:
        app.state.es = await connect_elasticsearch()
        await app.state.es.info()
        print("Elasticsearch connected successfully")
    except Exception as e:
        print(f"Elasticsearch connection failed: {e}")
        await close_elasticsearch()
        await RabbitMQ.close()
        await redis_client.close()
        await engine.dispose()
        raise

    accept_task = asyncio.create_task(auto_accept_pending_orders())

    yield

    accept_task.cancel()
    try:
        await accept_task
    except asyncio.CancelledError:
        pass

    print("Shutting down FastAPI application...")
    await RabbitMQ.close()
    await redis_client.close()
    await close_elasticsearch()
    await engine.dispose()
    print("Connections closed")

app = FastAPI(lifespan=lifespan, title="This is my ecommerce application")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registering routes
app.include_router(cart_routes)
app.include_router(category_routes)
app.include_router(customer_routes)
app.include_router(order_routes)
app.include_router(product_routes)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
