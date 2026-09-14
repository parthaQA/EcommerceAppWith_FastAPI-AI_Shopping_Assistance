import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from redis.asyncio import Redis

from src.cart.router import cart_routes
from src.category.router import category_routes
from src.customers.router import customer_routes
from src.order.router import order_routes
from src.products.router import product_routes
from src.utils.db import BASE, engine


BASE.metadata.create_all(engine)


load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

redis_client = Redis.from_url(
    REDIS_URL,
    decode_responses=True
)

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("Starting FastAPI application...")

    try:
        await redis_client.ping()
        print(f"Redis connected successfully: {REDIS_URL}")

    except Exception as e:
        print(f"Redis connection failed: {e}")
        raise

    yield

    print("Shutting down FastAPI application...")

    await redis_client.close()
    print("Redis connection closed")



app = FastAPI(lifespan=lifespan, title="This is my ecommerce application")

app.include_router(customer_routes)
app.include_router(category_routes)
app.include_router(product_routes)
app.include_router(cart_routes)
app.include_router(order_routes)


