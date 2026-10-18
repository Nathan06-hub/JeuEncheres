import hashlib
import hmac
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import create_access_token, aget_password_hash, averify_password
from app.api.deps import get_current_user
from app.models.user import User
from app.models.token import TokenTransaction, TokenTransactionType
from app.schemas.user import UserCreate, UserGuestLogin, UserResponse, Token
from app.core.config import settings

router = APIRouter()


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _token_response(user: User) -> dict[str, Any]:
    return {
        "access_token": create_access_token(subject=str(user.id)),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post(
    "/guest-login",
    response_model=Token,
    summary="Connexion / Inscription rapide via Mobile Device ID + secret d'appareil",
    dependencies=[Depends(rate_limit("guest-login"))],
)
async def guest_login(
    payload: UserGuestLogin,
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Onboarding instantané : le `device_id` seul ne suffit plus, il faut le `device_secret` aléatoire
    (stocké dans le Keychain/Keystore) dont seul le hash SHA-256 est conservé côté serveur."""
    secret_hash = _hash_secret(payload.device_secret)

    async def _load() -> User | None:
        res = await session.execute(select(User).where(User.device_id == payload.device_id))
        return res.scalar_one_or_none()

    user = await _load()

    if user is None:
        user = User(
            device_id=payload.device_id,
            device_secret_hash=secret_hash,
            username=f"guest_{uuid.uuid4().hex[:8]}",
            avatar_url=str(payload.avatar_url) if payload.avatar_url else None,
            token_balance=settings.INITIAL_FREE_TOKENS,
        )
        try:
            async with session.begin_nested():
                session.add(user)
                await session.flush()
                session.add(TokenTransaction(
                    user_id=user.id,
                    amount=settings.INITIAL_FREE_TOKENS,
                    balance_after=settings.INITIAL_FREE_TOKENS,
                    transaction_type=TokenTransactionType.INITIAL_GIFT,
                    metadata_json={"onboarding": "mobile_guest_gift"},
                ))
                await session.flush()
        except IntegrityError:
            # Course : une requête concurrente a créé le compte entre le SELECT et l'INSERT.
            user = await _load()
            if user is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Conflit à la création du compte")
        else:
            await session.commit()
            await session.refresh(user)
            return _token_response(user)

    if user.device_secret_hash is None:
        # Compte invité antérieur à l'introduction du secret : le premier secret présenté est adopté.
        user.device_secret_hash = secret_hash
        await session.commit()
    elif not hmac.compare_digest(user.device_secret_hash, secret_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants d'appareil invalides")

    if not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Compte utilisateur inactif")
    return _token_response(user)


@router.post(
    "/register",
    response_model=UserResponse,
    summary="Créer un compte complet",
    dependencies=[Depends(rate_limit("register"))],
)
async def register(
    payload: UserCreate,
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Création d'un compte avec nom d'utilisateur et mot de passe."""
    conflict = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Ce nom d'utilisateur ou cet email est déjà utilisé",
    )
    conditions = [User.username == payload.username]
    if payload.email:
        conditions.append(User.email == payload.email)
    res = await session.execute(select(User.id).where(or_(*conditions)))
    if res.first():
        raise conflict

    hashed_pw = await aget_password_hash(payload.password)
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hashed_pw,
        avatar_url=payload.avatar_url,
        token_balance=settings.INITIAL_FREE_TOKENS,
    )
    try:
        async with session.begin_nested():
            session.add(user)
            await session.flush()
            session.add(TokenTransaction(
                user_id=user.id,
                amount=settings.INITIAL_FREE_TOKENS,
                balance_after=settings.INITIAL_FREE_TOKENS,
                transaction_type=TokenTransactionType.INITIAL_GIFT,
                metadata_json={"source": "registration"},
            ))
            await session.flush()
    except IntegrityError:
        raise conflict
    await session.commit()
    await session.refresh(user)
    return user


# Hash factice : égalise le temps de réponse quand l'utilisateur n'existe pas (anti-énumération).
_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO5kTq7V6x3ZQe9pXk0qk9m6Qh1p2lq7e"


@router.post(
    "/token",
    response_model=Token,
    summary="Connexion classique JWT",
    dependencies=[Depends(rate_limit("login"))],
)
async def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Obtenir un jeton d'accès via identifiant et mot de passe."""
    query = select(User).where(
        or_(User.username == form_data.username, User.email == form_data.username)
    )
    res = await session.execute(query)
    user = res.scalar_one_or_none()

    hashed = user.hashed_password if user and user.hashed_password else _DUMMY_HASH
    valid = await averify_password(form_data.password, hashed)
    if not user or not user.hashed_password or not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant ou mot de passe incorrect",
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Compte utilisateur inactif")

    return _token_response(user)


@router.get("/me", response_model=UserResponse, summary="Profil utilisateur connecté")
async def get_me(current_user: User = Depends(get_current_user)) -> Any:
    return current_user
