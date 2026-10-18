"""Limitation de débit par IP : compteur Redis (INCR + EXPIRE) avec repli mémoire si Redis est indisponible."""
import logging
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_memory_hits: Dict[str, Deque[float]] = defaultdict(deque)


async def _hit_redis(key: str, window: int) -> int | None:
    from app.core import redis as redis_module

    client = redis_module.redis_client
    if client is None:
        return None
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window)
        return int(count)
    except Exception as exc:
        logger.warning("Rate limit Redis indisponible: %s", exc)
        return None


def _hit_memory(key: str, window: int) -> int:
    now = time.monotonic()
    hits = _memory_hits[key]
    while hits and now - hits[0] > window:
        hits.popleft()
    hits.append(now)
    return len(hits)


def rate_limit(scope: str, attempts: int | None = None, window: int | None = None):
    """Dépendance FastAPI : `Depends(rate_limit("login"))`."""

    async def _dependency(request: Request) -> None:
        max_attempts = attempts or settings.AUTH_RATE_LIMIT_ATTEMPTS
        win = window or settings.AUTH_RATE_LIMIT_WINDOW_SECONDS
        ip = request.client.host if request.client else "unknown"
        key = f"rl:{scope}:{ip}"
        count = await _hit_redis(key, win)
        if count is None:
            count = _hit_memory(key, win)
        if count > max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Trop de tentatives, réessayez plus tard",
                headers={"Retry-After": str(win)},
            )

    return _dependency
