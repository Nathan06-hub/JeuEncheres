import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.config import settings
from app.core.database import init_db_extensions, engine
from app.core.redis import init_redis_pool, close_redis_pool
from app.api.v1.api import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager handling startup & shutdown operations."""
    # Startup
    try:
        await init_db_extensions()
    except Exception:
        logger.exception("Could not initialize PostgreSQL extensions")
        if not settings.IS_DEVELOPMENT:
            raise  # hors développement : mieux vaut ne pas démarrer qu'être « healthy » sans base

    try:
        await init_redis_pool()
    except Exception:
        logger.exception("Could not connect to Redis pool")

    try:
        from app.services.timer_manager import timer_manager
        resumed = await timer_manager.resume_active_games()
        if resumed:
            logger.info("%d partie(s) en cours reprise(s) après redémarrage", resumed)
    except Exception:
        logger.exception("Could not resume active auction timers")

    yield

    # Shutdown
    from app.services.timer_manager import timer_manager
    for sess_id in list(timer_manager.running_timers):
        task = timer_manager.running_timers.pop(sess_id, None)
        if task and not task.done():
            task.cancel()
    await close_redis_pool()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# CORS Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials="*" not in settings.BACKEND_CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)


async def _collect_checks() -> dict:
    checks = {"postgres": False, "redis": False}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        logger.warning("Health check: PostgreSQL indisponible")

    try:
        from app.core import redis as redis_module
        if redis_module.redis_client is not None:
            await redis_module.redis_client.ping()
            checks["redis"] = True
    except Exception:
        logger.warning("Health check: Redis indisponible")
    return checks


def _body(checks: dict) -> dict:
    # Redis est optionnel (repli mémoire) : dégradé mais fonctionnel
    if checks["postgres"] and checks["redis"]:
        state = "healthy"
    elif checks["postgres"]:
        state = "degraded"
    else:
        state = "unhealthy"
    return {
        "status": state,
        "checks": checks,
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe : le process répond (200 toujours) ; l'état des dépendances est dans `checks`."""
    return _body(await _collect_checks())


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """Readiness probe : 503 si PostgreSQL est indisponible (à utiliser pour l'orchestrateur / load balancer)."""
    body = _body(await _collect_checks())
    return JSONResponse(status_code=200 if body["checks"]["postgres"] else 503, content=body)