import asyncio
import logging
import re
import uuid
from typing import Any, Dict, List, Set

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.deck import Deck, DeckItem, DeckCategory
from app.schemas.deck import DeckGenerateRequest, DeckDetailResponse
from app.services.gemini_service import GeminiService
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)

router = APIRouter()

GENERATION_TIMEOUT_SECONDS = 25.0
EMBEDDING_TIMEOUT_SECONDS = 15.0

# Générations en cours par utilisateur (process local) : empêche de lancer N générations Gemini
# en parallèle avec un seul jeton (les débits suivants échoueraient *après* avoir coûté un appel IA).
# Repli local si Redis est indisponible
_generations_in_flight: Set[uuid.UUID] = set()
GENERATION_LOCK_TTL_SECONDS = 60


async def _acquire_generation_lock(user_id: uuid.UUID, ttl_seconds: int = GENERATION_LOCK_TTL_SECONDS) -> tuple[bool, str]:
    token = uuid.uuid4().hex
    lock_key = f"lock:deck_generation:{user_id}"
    from app.core import redis as redis_module
    client = redis_module.redis_client
    if client is not None:
        try:
            acquired = await client.set(lock_key, token, nx=True, ex=ttl_seconds)
            if not acquired:
                return False, ""
            return True, token
        except Exception as exc:
            logger.warning("Verrou Redis indisponible pour %s, repli memoire: %s", lock_key, exc)

    if user_id in _generations_in_flight:
        return False, ""
    _generations_in_flight.add(user_id)
    return True, "memory"


async def _release_generation_lock(user_id: uuid.UUID, lock_token: str) -> None:
    if not lock_token:
        return
    if lock_token == "memory":
        _generations_in_flight.discard(user_id)
        return

    lock_key = f"lock:deck_generation:{user_id}"
    from app.core import redis as redis_module
    client = redis_module.redis_client
    if client is not None:
        try:
            lua_release = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """
            await client.eval(lua_release, 1, lock_key, lock_token)
        except Exception as exc:
            logger.warning("Erreur liberation verrou Redis pour %s: %s", lock_key, exc)
    _generations_in_flight.discard(user_id)


class _AIItem(BaseModel):
    """Validation stricte de la sortie du LLM : rien n'est écrit en base sans passer ici."""
    name: str = Field(..., min_length=1, max_length=180)
    clue_1: str = Field(..., min_length=1, max_length=500)
    clue_2: str = Field(..., min_length=1, max_length=500)
    clue_3: str = Field(..., min_length=1, max_length=500)
    base_score: int = Field(..., ge=1, le=100)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("base_score", mode="before")
    @classmethod
    def _coerce_score(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("base_score invalide")
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
        return v


@router.get("/suggestions", summary="📱 Écran 02 : Chips de suggestions rapides d'inspiration")
async def get_inspiration_chips() -> List[str]:
    """Liste de suggestions tendance pour inspirer le joueur dans sa création IA."""
    return [
        "Films de SF des années 90",
        "Légendes du Football Moderne",
        "Animés Culte & Shōnen",
        "Grandes Batailles de l'Histoire",
        "Monuments & Merveilles du Monde",
        "Séries Culte HBO & Netflix",
        "Jeux Vidéo Rétro des années 80-90",
        "Rock & Légendes de la Musique",
    ]


def _validate_ai_items(raw_items: Any, expected: int) -> List[_AIItem]:
    if not isinstance(raw_items, list):
        raise ValueError("items absent")
    valid: List[_AIItem] = []
    seen: Set[str] = set()
    for raw in raw_items:
        try:
            item = _AIItem.model_validate(raw)
        except ValidationError:
            continue
        key = item.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        valid.append(item)
    # Un deck jouable exige au moins 5 cartes valides et dédoublonnées
    if len(valid) < min(5, expected):
        raise ValueError("Pas assez d'items valides générés")
    return valid[:expected]


@router.post("/generate", response_model=DeckDetailResponse, summary="📱 Écran 02 : Générer un deck complet via Gemini API (Déduction 1 Jeton)")
async def generate_ai_deck(
    payload: DeckGenerateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Saisie d'un sujet libre -> appel Gemini API -> déduction 1 jeton -> stockage PostgreSQL avec 3 indices et score 1-100."""
    user_id = current_user.id
    cost = settings.AI_DECK_CREATION_TOKEN_COST

    lock_acquired, lock_token = await _acquire_generation_lock(user_id)
    if not lock_acquired:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Une generation est deja en cours")
    try:
        # 1. Vérifie le solde, puis RELÂCHE la connexion DB avant l'appel IA (jusqu'à 25 s) :
        #    sinon chaque génération immobilise une connexion du pool pendant tout l'appel.
        balance = await TokenService.get_user_balance(session, user_id)
        await session.rollback()
        if balance < cost:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Solde de jetons insuffisant (Requis: {cost}, Actuel: {balance})",
            )

        # 2. Appel Gemini (deck + embeddings en parallèle) sous un timeout global
        gemini = GeminiService()
        try:
            deck_data = await asyncio.wait_for(
                gemini.generate_deck(
                    prompt=payload.prompt,
                    category=payload.category,
                    items_count=payload.items_count,
                ),
                timeout=GENERATION_TIMEOUT_SECONDS,
            )
            ai_items = _validate_ai_items(deck_data.get("items"), payload.items_count)
            embeddings = await asyncio.wait_for(
                asyncio.gather(*(gemini.get_embedding(f"{i.name}: {i.clue_3}") for i in ai_items)),
                timeout=EMBEDDING_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="La génération a pris trop de temps. Aucun jeton n'a été débité.")
        except HTTPException:
            raise
        except Exception:
            logger.exception("Échec de la génération IA")
            raise HTTPException(status_code=502, detail="La génération IA a échoué. Aucun jeton n'a été débité.")

        # 3. Débit atomique (verrou de ligne) seulement une fois la génération validée
        await TokenService.deduct_deck_creation_token(
            session=session,
            user_id=user_id,
            deck_title=payload.prompt,
        )

        # 4. Création du deck (slug garanti unique)
        title = str(deck_data.get("title") or payload.prompt)[:150]
        slug_base = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:120] or "deck"
        slug = f"{slug_base}-{uuid.uuid4().hex[:8]}"

        cat_str = deck_data.get("category", "Pop Culture")
        try:
            deck_category = DeckCategory(cat_str)
        except ValueError:
            deck_category = payload.category or DeckCategory.POP_CULTURE
            cat_str = deck_category.value

        tags = deck_data.get("tags")
        if not isinstance(tags, list):
            tags = [cat_str]

        deck = Deck(
            creator_id=user_id,
            title=title,
            slug=slug,
            description=str(deck_data.get("description") or f"Deck thématique généré par IA autour de : {payload.prompt}")[:2000],
            category=deck_category,
            tags=[str(t)[:50] for t in tags[:10]],
            is_public=True,
            ai_prompt=payload.prompt,
        )
        session.add(deck)
        await session.flush()

        items = [
            DeckItem(
                deck_id=deck.id,
                name=item.name,
                clue_1=item.clue_1,
                clue_2=item.clue_2,
                clue_3=item.clue_3,
                base_score=item.base_score,
                rarity=GeminiService._calculate_rarity(item.base_score),
                category=cat_str,
                embedding=embedding,
                metadata_json=item.metadata,
            )
            for item, embedding in zip(ai_items, embeddings)
        ]
        session.add_all(items)
        await session.commit()
        await session.refresh(deck)

        deck_items_res = await session.execute(
            select(DeckItem).where(DeckItem.deck_id == deck.id).order_by(DeckItem.base_score.desc())
        )
        deck.items = list(deck_items_res.scalars().all())
        return deck
    finally:
        await _release_generation_lock(user_id, lock_token)
