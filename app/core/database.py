from collections.abc import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


_is_sqlite = settings.ASYNC_DATABASE_URI.startswith("sqlite")
_engine_kwargs = (
    {"connect_args": {"check_same_thread": False}}
    if _is_sqlite
    else {"pool_pre_ping": True, "pool_size": 20, "max_overflow": 10}
)

# Engine with connection pooling
engine = create_async_engine(
    settings.ASYNC_DATABASE_URI,
    echo=settings.SQL_ECHO,
    **_engine_kwargs,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db_extensions() -> None:
    """Initialize required PostgreSQL extensions (pgvector & uuid-ossp) or local SQLite tables."""
    async with engine.begin() as conn:
        if _is_sqlite:
            from app.models.base import Base
            await conn.run_sync(Base.metadata.create_all)
        else:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for database sessions with automatic rollback on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
