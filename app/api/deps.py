import uuid
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/token",
    auto_error=False,
)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_user_id(token: str) -> uuid.UUID:
    """Décode le JWT et retourne l'UUID utilisateur ; lève 401 si le token est invalide."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
        if payload.get("type", "access") != "access":
            raise _unauthorized("Type de jeton invalide")
        return uuid.UUID(str(payload["sub"]))
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise _unauthorized("Jeton d'authentification invalide ou expiré")


async def get_current_user_optional(
    session: AsyncSession = Depends(get_db),
    token: Optional[str] = Depends(reusable_oauth2),
) -> Optional[User]:
    """Return current user if valid bearer token is present, else None."""
    if not token:
        return None
    try:
        user_id = decode_user_id(token)
    except HTTPException:
        return None

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(
    session: AsyncSession = Depends(get_db),
    token: Optional[str] = Depends(reusable_oauth2),
) -> User:
    """Enforce authenticated user requirement."""
    if not token:
        raise _unauthorized("Jeton d'authentification manquant")

    user_id = decode_user_id(token)
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        # 401 (et non 404) : le client doit se reconnecter / purger son token
        raise _unauthorized("Utilisateur introuvable")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte utilisateur inactif",
        )
    return user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privilèges administrateur requis",
        )
    return current_user


async def get_game_or_404(session: AsyncSession, session_id: uuid.UUID):
    """Récupère une GameSession par son ID ou lève une HTTPException 404."""
    from app.models.game import GameSession
    game_res = await session.execute(select(GameSession).where(GameSession.id == session_id))
    game = game_res.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Session d'enchères introuvable")
    return game


async def ensure_participant(session: AsyncSession, game, user: User) -> None:
    """Vérifie que l'utilisateur est l'hôte ou un participant inscrit de la session."""
    from app.models.game import GameSessionPlayer
    if game.host_id == user.id:
        return
    row = (await session.execute(
        select(GameSessionPlayer.id).where(
            GameSessionPlayer.session_id == game.id,
            GameSessionPlayer.user_id == user.id,
        ).limit(1)
    )).first()
    if not row:
        raise HTTPException(status_code=403, detail="Vous ne participez pas à cette partie")

