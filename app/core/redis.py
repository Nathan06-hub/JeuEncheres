from collections.abc import AsyncGenerator
import redis.asyncio as aioredis
from app.core.config import settings

redis_client: aioredis.Redis | None = None


async def init_redis_pool() -> aioredis.Redis:
    """Initialize Redis connection pool."""
    global redis_client
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    return redis_client


async def close_redis_pool() -> None:
    """Close Redis pool during app shutdown."""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Dependency injection for Redis client."""
    global redis_client
    if redis_client is None:
        redis_client = await init_redis_pool()
    yield redis_client
