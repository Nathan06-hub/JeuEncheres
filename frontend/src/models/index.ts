export type ScreenId = 'home' | 'creation' | 'auction' | 'results' | 'shop';

export type DeckCategory = 
  | 'ALL'
  | 'POP_CULTURE'
  | 'CINEMA'
  | 'SPORT'
  | 'HISTOIRE'
  | 'MANGAS'
  | 'MUSIQUE'
  | 'JEUX_VIDEO'
  | 'Pop Culture';

export type ItemRarity = 'common' | 'rare' | 'epic' | 'legendary' | 'COMMON' | 'RARE' | 'EPIC' | 'LEGENDARY';

export interface DeckItem {
  id: string;
  name: string;
  clue1: string;
  clue2: string;
  clue3: string;
  score: number;
  rarity: ItemRarity;
  category: string;
  winningBid?: number;
  clueLevelWon?: number;
}

export interface Deck {
  id: string;
  title: string;
  category: DeckCategory;
  author?: string;
  itemsCount: number;
  rating?: number;
  playCount?: number;
  badge?: string;
  description: string;
  items?: DeckItem[];
  slug?: string;
}

export interface Player {
  id: string;
  name: string;
  avatar?: string;
  isCurrentUser: boolean;
  budget: number;
  currentBid: number;
  hasPassed: boolean;
  score: number;
  draftedItems: DeckItem[];
}

export interface AuctionRound {
  roundNumber: number;
  totalRounds: number;
  item: DeckItem;
  revealedCluesCount: number; // 1, 2, 3
  timeRemaining: number; // seconds
  highestBid: number;
  highestBidderId: string | null;
  highestBidderName?: string | null;
}

export interface GameSession {
  id: string;
  code?: string;
  deck: Deck;
  currentRound: AuctionRound;
  players: Player[];
  status: 'LOBBY' | 'ROUND_BIDDING' | 'ROUND_REVEAL' | 'FINISHED' | 'WAITING' | 'IN_PROGRESS' | 'COMPLETED';
}

export interface ShopPack {
  id: string;
  sku?: string;
  tokens: number;
  price: string;
  priceCents?: number;
  bonusTokens?: number;
  isPopular?: boolean;
  badge?: string;
}

export interface Transaction {
  id: string;
  title: string;
  date: string;
  amount: number; // +1, -1, +15
  type: 'gain' | 'spend';
}

export interface PodiumEntry {
  player_id: string;
  display_name: string;
  rank: number;
  final_score: number;
  roi_percentage: number;
  remaining_budget: number;
}

export interface PlayerDraftComposition {
  player_id: string;
  display_name: string;
  avatar_url?: string | null;
  remaining_budget: number;
  spent_budget: number;
  base_score_total: number;
  synergy_bonus: number;
  final_score: number;
  roi_percentage: number;
  rank: number;
  items: Array<{
    id: string;
    name: string;
    base_score: number;
    rarity: string;
    category?: string;
    winning_bid: number;
    clue_level_won: number;
  }>;
  synergies_breakdown: Array<{
    name: string;
    bonus: number;
    description: string;
  }>;
}

export interface GameResultsResponse {
  session_id: string;
  deck_title: string;
  total_rounds: number;
  podium: PodiumEntry[];
  compositions: PlayerDraftComposition[];
}

export interface UserProfile {
  id: string;
  username: string;
  tokenBalance: number;
  avatarUrl?: string | null;
  isAuthenticated: boolean;
}


export type GamePlayMode = 'LOCAL' | 'ONLINE';

export interface LocalMatchResults {
  deckTitle: string;
  totalRounds: number;
  podium: PodiumEntry[];
  compositions: PlayerDraftComposition[];
}
