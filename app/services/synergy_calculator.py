# -*- coding: utf-8 -*-
import uuid
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.game import GameSession, GameSessionPlayer
from app.models.bid import DraftedItem
from app.models.deck import Deck, DeckItem


class SynergyCalculator:
    """Calculates team composition synergies and ROI for Screen 04 Results."""

    @staticmethod
    def _cosine_similarity(vec_a: Any, vec_b: Any) -> float:
        """Calcule la similarite cosinus entre deux vecteurs d'embeddings (768-dim)."""
        if not vec_a or not vec_b:
            return 0.0
        try:
            dot = sum(a * b for a, b in zip(vec_a, vec_b))
            norm_a = sum(a * a for a in vec_a) ** 0.5
            norm_b = sum(b * b for b in vec_b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)
        except Exception:
            return 0.0

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

        # Une seule requete pour toutes les cartes remportees
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
                        "name": f"Synergie Thematique: {cat}",
                        "bonus": bonus,
                        "description": f"{count} items de la meme categorie ({cat})",
                    })

            # 2. High Rarity synergy: +20 pts if 2+ Epics/Legendaries
            elite_count = rarities_count.get("LEGENDARY", 0) + rarities_count.get("EPIC", 0)
            if elite_count >= 2:
                bonus = elite_count * 10
                synergy_bonus += bonus
                synergies_breakdown.append({
                    "name": "Synergie Elite",
                    "bonus": bonus,
                    "description": f"{elite_count} cartes Epiques ou Legendaires",
                })

            # 3. Clue 1 Bravery bonus: reward winning on subtle 1st clue!
            clue1_wins = sum(1 for d, _ in pairs if d.clue_level_won == 1)
            if clue1_wins > 0:
                bonus = clue1_wins * 10
                synergy_bonus += bonus
                synergies_breakdown.append({
                    "name": "Instinct Pur",
                    "bonus": bonus,
                    "description": f"{clue1_wins} encheres gagnees des le 1er indice",
                })

            # 4. Semantic Coherence bonus: reward thematic closeness via pgvector embeddings
            embedded_items = [item for _, item in pairs if getattr(item, "embedding", None) is not None]
            if len(embedded_items) >= 2:
                sims = []
                for i in range(len(embedded_items)):
                    for j in range(i + 1, len(embedded_items)):
                        sim = cls._cosine_similarity(embedded_items[i].embedding, embedded_items[j].embedding)
                        sims.append(sim)
                if sims:
                    avg_sim = sum(sims) / len(sims)
                    if avg_sim >= 0.65:
                        bonus = int(round(avg_sim * 20))
                        synergy_bonus += bonus
                        synergies_breakdown.append({
                            "name": "Harmonie Semantique",
                            "bonus": bonus,
                            "description": f"Deck a forte coherence semantique ({int(avg_sim * 100)}% de proximite vectorielle)",
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
            "deck_title": deck.title if deck else "Theme",
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
