import { DeckItem, PodiumEntry, PlayerDraftComposition } from '../models';

export interface LocalPlayerState {
  id: string;
  name: string;
  startingBudget: number;
  remainingBudget: number;
  spentBudget: number;
  draftedItems: DeckItem[];
}

export interface LocalMatchResults {
  deckTitle: string;
  totalRounds: number;
  podium: PodiumEntry[];
  compositions: PlayerDraftComposition[];
}

export function computeLocalGameResults(
  deckTitle: string,
  totalRounds: number,
  players: LocalPlayerState[]
): LocalMatchResults {
  const compositions: PlayerDraftComposition[] = [];

  for (const p of players) {
    const items = p.draftedItems || [];
    const spentBudget = items.reduce((sum, item) => sum + (item.winningBid || 0), 0);
    const baseScoreTotal = items.reduce((sum, item) => sum + (item.score || 0), 0);

    const categoriesCount: Record<string, number> = {};
    const raritiesCount: Record<string, number> = {};
    let clue1Wins = 0;

    for (const item of items) {
      const cat = item.category || 'Universal';
      categoriesCount[cat] = (categoriesCount[cat] || 0) + 1;

      const rarity = (item.rarity || 'common').toUpperCase();
      raritiesCount[rarity] = (raritiesCount[rarity] || 0) + 1;

      if (item.clueLevelWon === 1 || item.clueLevelWon === undefined) {
        clue1Wins += 1;
      }
    }

    // Calcul des synergies
    let synergyBonus = 0;
    const synergiesBreakdown: Array<{ name: string; bonus: number; description: string }> = [];

    // 1. Synergie Thématique : 3+ cartes de la même catégorie (+5 pts par carte)
    for (const [cat, count] of Object.entries(categoriesCount)) {
      if (count >= 3) {
        const bonus = count * 5;
        synergyBonus += bonus;
        synergiesBreakdown.push({
          name: `Synergie Thématique: ${cat}`,
          bonus,
          description: `${count} cartes du même univers (${cat})`,
        });
      }
    }

    // 2. Synergie Élite : 2+ cartes Épiques ou Légendaires (+10 pts par carte)
    const eliteCount = (raritiesCount['LEGENDARY'] || 0) + (raritiesCount['EPIC'] || 0);
    if (eliteCount >= 2) {
      const bonus = eliteCount * 10;
      synergyBonus += bonus;
      synergiesBreakdown.push({
        name: 'Synergie Élite',
        bonus,
        description: `${eliteCount} cartes Épiques ou Légendaires`,
      });
    }

    // 3. Instinct Pur : cartes gagnées dès le 1er indice (+10 pts par carte)
    if (clue1Wins > 0) {
      const bonus = clue1Wins * 10;
      synergyBonus += bonus;
      synergiesBreakdown.push({
        name: 'Instinct Pur',
        bonus,
        description: `${clue1Wins} enchère(s) gagnée(s) dès le 1er indice`,
      });
    }

    const finalScore = baseScoreTotal + synergyBonus;
    // ROI = score final divisé par budget dépensé (ex: 2.50 = +150% de rendement)
    const roiPercentage = spentBudget > 0 ? Number((finalScore / spentBudget).toFixed(2)) : Number(finalScore.toFixed(2));

    compositions.push({
      player_id: p.id,
      display_name: p.name,
      avatar_url: null,
      remaining_budget: p.remainingBudget,
      spent_budget: spentBudget,
      base_score_total: baseScoreTotal,
      synergy_bonus: synergyBonus,
      final_score: finalScore,
      roi_percentage: roiPercentage,
      rank: 1, // updated after sorting
      items: items.map((item) => ({
        id: item.id,
        name: item.name,
        base_score: item.score,
        rarity: item.rarity,
        category: item.category,
        winning_bid: item.winningBid || 0,
        clue_level_won: item.clueLevelWon || 1,
      })),
      synergies_breakdown: synergiesBreakdown,
    });
  }

  // Tri par score final décroissant (départage par budget restant)
  compositions.sort((a, b) => {
    if (b.final_score !== a.final_score) {
      return b.final_score - a.final_score;
    }
    return b.remaining_budget - a.remaining_budget;
  });

  const podium: PodiumEntry[] = [];
  compositions.forEach((comp, idx) => {
    comp.rank = idx + 1;
    podium.push({
      player_id: comp.player_id,
      display_name: comp.display_name,
      rank: comp.rank,
      final_score: comp.final_score,
      roi_percentage: comp.roi_percentage,
      remaining_budget: comp.remaining_budget,
    });
  });

  return {
    deckTitle,
    totalRounds,
    podium,
    compositions,
  };
}
