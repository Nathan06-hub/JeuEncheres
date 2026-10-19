"""Limitation de débit par IP : compteur Redis atomique (Lua INCR + EXPIRE) avec repli mémoire borné."""
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_MEMORY_KEYS = 4096
_memory_hits: Dict[str, Deque[float]] = {}
_memory_daily_counters: Dict[str, int] = {}

_LUA_INCR_EXPIRE = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
else
    local ttl = redis.call('TTL', KEYS[1])
    if ttl < 0 then
        redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
    end
end
return current
"""


async def _hit_redis(key: str, window: int) -> int | None:
    from app.core import redis as redis_module

    client = redis_module.redis_client
    if client is None:
        return None
    try:
        count = await client.eval(_LUA_INCR_EXPIRE, 1, key, window)
        return int(count)
    except Exception as exc:
        logger.warning("Rate limit Redis indisponible: %s", exc)
        return None


def _hit_memory(key: str, window: int) -> int:
    now = time.monotonic()
    if key not in _memory_hits and len(_memory_hits) >= _MAX_MEMORY_KEYS:
        # Purge des clés expirées ou de la plus ancienne entrée
        expired = [k for k, dq in _memory_hits.items() if not dq or now - dq[-1] > window]
        for k in expired:
            _memory_hits.pop(k, None)
        if len(_memory_hits) >= _MAX_MEMORY_KEYS:
            oldest_key = next(iter(_memory_hits))
            _memory_hits.pop(oldest_key, None)

    hits = _memory_hits.setdefault(key, deque())
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


async def enforce_daily_global_quota(scope: str, daily_cap: int) -> None:
    """Vérifie et incrémente un quota global journalier (ex: plafond de générations IA par jour)."""
    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"quota:daily:{scope}:{day_key}"
    count = await _hit_redis(key, 86400 + 3600)
    if count is None:
        if len(_memory_daily_counters) > 64:
            _memory_daily_counters.clear()
        count = _memory_daily_counters.get(key, 0) + 1
        _memory_daily_counters[key] = count
    if count > daily_cap:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Quota journalier global de générations IA atteint, réessayez demain",
        )

