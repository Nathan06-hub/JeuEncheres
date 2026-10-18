import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
import bcrypt
from app.core.config import settings


def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    """Generate signed JWT access token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash (bloquant : utiliser averify_password dans une route async)."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    """Generate bcrypt hash for password (bloquant : utiliser aget_password_hash dans une route async)."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


async def averify_password(plain_password: str, hashed_password: str) -> bool:
    """bcrypt est CPU-bound (~100 ms) : exécuté dans un thread pour ne pas bloquer la boucle d'événements."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


async def aget_password_hash(password: str) -> str:
    return await asyncio.to_thread(get_password_hash, password)
