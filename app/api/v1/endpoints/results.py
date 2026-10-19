import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, ensure_participant, get_game_or_404
from app.core.database import get_db
from app.models.game import GameStatus
from app.models.user import User
from app.schemas.game import GameResultsResponse
from app.services.synergy_calculator import SynergyCalculator

router = APIRouter()


@router.get(
    "/sessions/{session_id}/results",
    response_model=GameResultsResponse,
    summary="📱 Écran 04 : Résultats, calcul des synergies d'équipe, ROI et classement final",
)
async def get_game_results(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Calcule et retourne le podium, les compositions complètes et les bonus de synergie IA.

    Réservé aux participants, et uniquement une fois la partie terminée (le calcul écrit en base :
    il ne doit pas pouvoir être déclenché à volonté par n'importe qui en cours de partie)."""
    game = await get_game_or_404(session, session_id)
    await ensure_participant(session, game, current_user)
    if game.status != GameStatus.FINISHED:
        raise HTTPException(status_code=409, detail="La partie n'est pas terminée")

    already_computed = game.players and all(p.rank is not None for p in game.players)
    results = await SynergyCalculator.compute_game_results(session=session, session_id=session_id)
    if not results:
        raise HTTPException(status_code=404, detail="Partie introuvable")
    if not already_computed:
        await session.commit()
    return results
