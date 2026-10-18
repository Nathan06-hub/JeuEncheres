import uuid
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.game import GameSession, GameSessionPlayer
from app.models.bid import DraftedItem
from app.models.deck import Deck, DeckItem


class SynergyCalculator:
    """Calculates team composition synergies and ROI for Screen 04 Results."""

    @classmethod
    async def compute_game_results(
        cls,
        session: AsyncSession,
        session_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Compute all players' final scores, synergy bonuses, ROI and podium ranking."""
        game_res = await session.execute(select(GameSession).where(GameSession.id == session_id))
        game = game_res.scalar_one_or_none()
        if not game:
            return {}

        deck_res = await session.execute(select(Deck).where(Deck.id == game.deck_id))
        deck = deck_res.scalar_one_or_none()

        players_res = await session.execute(
            select(GameSessionPlayer).where(GameSessionPlayer.session_id == session_id)
        )
        players = list(players_res.scalars().all())

        compositions = []

        # Une seule requête pour toutes les cartes remportées (évite 1 requête par joueur)
        all_pairs_res = await session.execute(
            select(DraftedItem, DeckItem)
            .join(DeckItem, DraftedItem.item_id == DeckItem.id)
            .where(DraftedItem.session_id == session_id)
            .order_by(DraftedItem.round_number.asc())
        )
        pairs_by_player: Dict[uuid.UUID, list] = {}
        for drafted_row, item_row in all_pairs_res.all():
            pairs_by_player.setdefault(drafted_row.player_id, []).append((drafted_row, item_row))

        for p in players:
            pairs = pairs_by_player.get(p.id, [])

            won_items_data = []
            categories_count: Dict[str, int] = {}
            rarities_count: Dict[str, int] = {}
            spent_budget = 0

            for drafted, item in pairs:
                spent_budget += drafted.winning_bid_amount
                won_items_data.append({
                    "id": str(item.id),
                    "name": item.name,
                    "base_score": item.base_score,
                    "rarity": item.rarity.value,
                    "category": item.category,
                    "winning_bid": drafted.winning_bid_amount,
                    "clue_level_won": drafted.clue_level_won,
                })

                cat = item.category or "Universal"
                categories_count[cat] = categories_count.get(cat, 0) + 1
                rarities_count[item.rarity.value] = rarities_count.get(item.rarity.value, 0) + 1

            # Compute synergy bonuses
            synergy_bonus = 0
            synergies_breakdown = []

            # 1. Category alignment bonus: +15 pts if 3+ cards from same category
            for cat, count in categories_count.items():
                if count >= 3:
                    bonus = count * 5
                    synergy_bonus += bonus
                    synergies_breakdown.append({
                        "name": f"Synergie Thématique: {cat}",
                        "bonus": bonus,
                        "description": f"{count} items de la même catégorie ({cat})",
                    })

            # 2. High Rarity synergy: +20 pts if 2+ Epics/Legendaries
            elite_count = rarities_count.get("LEGENDARY", 0) + rarities_count.get("EPIC", 0)
            if elite_count >= 2:
                bonus = elite_count * 10
                synergy_bonus += bonus
                synergies_breakdown.append({
                    "name": "Synergie Élite",
                    "bonus": bonus,
                    "description": f"{elite_count} cartes Épiques ou Légendaires",
                })

            # 3. Clue 1 Bravery bonus: reward winning on subtle 1st clue!
            clue1_wins = sum(1 for d, _ in pairs if d.clue_level_won == 1)
            if clue1_wins > 0:
                bonus = clue1_wins * 10
                synergy_bonus += bonus
                synergies_breakdown.append({
                    "name": "Instinct Pur",
                    "bonus": bonus,
                    "description": f"{clue1_wins} enchères gagnées dès le 1er indice",
                })

            # Update player stats
            p.synergy_bonus = synergy_bonus
            p.final_score = p.base_score_total + synergy_bonus

            # ROI = (Final Score / Spent Budget)
            p.roi_percentage = round((p.final_score / spent_budget), 2) if spent_budget > 0 else float(p.final_score)

            compositions.append({
                "player_id": str(p.id),
                "display_name": p.display_name,
                "avatar_url": p.avatar_url,
                "remaining_budget": p.remaining_budget,
                "spent_budget": spent_budget,
                "base_score_total": p.base_score_total,
                "synergy_bonus": p.synergy_bonus,
                "final_score": p.final_score,
                "roi_percentage": p.roi_percentage,
                "items": won_items_data,
                "synergies_breakdown": synergies_breakdown,
            })

        # Rank players by final score desc
        players.sort(key=lambda x: x.final_score, reverse=True)
        for rank_idx, player in enumerate(players, start=1):
            player.rank = rank_idx
            # update in composition dict
            for comp in compositions:
                if comp["player_id"] == str(player.id):
                    comp["rank"] = rank_idx

        await session.flush()

        return {
            "session_id": str(game.id),
            "deck_title": deck.title if deck else "Thème",
            "total_rounds": game.total_rounds,
            "podium": [
                {
                    "player_id": str(p.id),
                    "display_name": p.display_name,
                    "rank": p.rank,
                    "final_score": p.final_score,
                    "roi_percentage": p.roi_percentage,
                    "remaining_budget": p.remaining_budget,
                }
                for p in players
            ],
            "compositions": compositions,
        }
