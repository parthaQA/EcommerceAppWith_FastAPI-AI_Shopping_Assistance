import redis.asyncio as redis

from src.utils.settings import settings

redis_client = redis.from_url(
    settings.REDIS_URL or "redis://localhost:6379/0",
    decode_responses=True,
)
