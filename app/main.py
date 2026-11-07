import logging
import logging.config
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.config import settings
from app.core.database import init_db_extensions, engine
from app.core.exceptions import DomainError
from app.core.redis import init_redis_pool, close_redis_pool
from app.api.v1.api import api_router

logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
            }
        },
        "root": {
            "handlers": ["console"],
            "level": "DEBUG" if settings.DEBUG else "INFO",
        },
    }
)

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
        redis_client = await init_redis_pool()
        await redis_client.ping()
    except Exception:
        logger.exception("Could not connect to Redis pool")
        if not settings.IS_DEVELOPMENT:
            raise

    try:
        from app.core.database import AsyncSessionLocal
        from app.api.v1.endpoints.shop import seed_default_token_packs
        async with AsyncSessionLocal() as session:
            await seed_default_token_packs(session)
    except Exception:
        logger.exception("Could not seed default token packs")

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
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.IS_DEVELOPMENT else None,
    docs_url=f"{settings.API_V1_STR}/docs" if settings.IS_DEVELOPMENT else None,
    redoc_url=f"{settings.API_V1_STR}/redoc" if settings.IS_DEVELOPMENT else None,
    lifespan=lifespan,
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})



@app.middleware("http")
async def security_and_correlation_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'",
    )
    if not settings.IS_DEVELOPMENT:
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return response


# Proxy headers middleware (reverse proxy client IP resolution for rate limiting)
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=settings.TRUSTED_PROXY_HOSTS,
)

# CORS Middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials="*" not in settings.BACKEND_CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
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
