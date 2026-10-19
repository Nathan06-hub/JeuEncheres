import {
  Deck,
  DeckCategory,
  DeckItem,
  GameResultsResponse,
  ShopPack,
  Transaction,
} from '../models';

const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000/api/v1';

// Device Identifiers & Storage
const STORAGE_KEYS = {
  DEVICE_ID: 'encheres_device_id',
  DEVICE_SECRET: 'encheres_device_secret',
  ACCESS_TOKEN: 'encheres_access_token',
};

export function getDeviceId(): string {
  let id = localStorage.getItem(STORAGE_KEYS.DEVICE_ID);
  if (!id) {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      id = `device_${crypto.randomUUID()}`;
    } else {
      const arr = new Uint8Array(16);
      if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
        crypto.getRandomValues(arr);
        id = `device_${Array.from(arr, (b) => b.toString(16).padStart(2, '0')).join('')}`;
      } else {
        id = `device_${Date.now().toString(36)}`;
      }
    }
    localStorage.setItem(STORAGE_KEYS.DEVICE_ID, id);
  }
  return id;
}

export function getDeviceSecret(): string {
  let secret = localStorage.getItem(STORAGE_KEYS.DEVICE_SECRET);
  if (!secret) {
    const arr = new Uint8Array(24);
    if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
      crypto.getRandomValues(arr);
      secret = Array.from(arr, (b) => b.toString(16).padStart(2, '0')).join('');
    } else {
      secret = `sec_${Date.now()}_longsecretkey32charactersfallback`;
    }
    localStorage.setItem(STORAGE_KEYS.DEVICE_SECRET, secret);
  }
  return secret;
}

export function getStoredToken(): string | null {
  return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
}

// Request Helper with Token & Error Handling
async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const token = getStoredToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `Erreur ${response.status}`;
    try {
      const errorJson = await response.json();
      errorDetail = errorJson.detail || errorJson.message || errorDetail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return response.json() as Promise<T>;
}

// Check Backend Health
export async function checkBackendHealth(): Promise<boolean> {
  try {
    const healthOrigin = API_BASE_URL.replace(/\/api\/v1\/?$/, '');
    const res = await fetch(`${healthOrigin}/health`, { method: 'GET', signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

// Auth: Guest Login
export async function ensureGuestAuth(): Promise<string> {
  const existing = getStoredToken();
  if (existing) return existing;

  const deviceId = getDeviceId();
  const deviceSecret = getDeviceSecret();

  const data = await request<{ access_token: string }>('/auth/guest-login', {
    method: 'POST',
    body: JSON.stringify({
      device_id: deviceId,
      device_secret: deviceSecret,
      display_name: `Joueur_${deviceId.slice(-4)}`,
    }),
  });

  setStoredToken(data.access_token);
  return data.access_token;
}

// Home & User Profile
export async function fetchHomeSummary(): Promise<{
  userBalance: number;
  username: string;
  avatarUrl?: string | null;
  activeLiveGames: number;
  categories: string[];
  isAuthenticated: boolean;
}> {
  try {
    const data = await request<any>('/home/summary');
    return {
      userBalance: data.user_balance ?? 3,
      username: data.username || 'Invité',
      avatarUrl: data.avatar_url,
      activeLiveGames: data.active_live_games ?? 0,
      categories: data.categories || [],
      isAuthenticated: data.is_authenticated ?? false,
    };
  } catch (err) {
    console.warn('Fallback home summary:', err);
    return {
      userBalance: 3,
      username: 'Invité',
      activeLiveGames: 2,
      categories: ['POP_CULTURE', 'CINEMA', 'SPORT', 'HISTOIRE', 'MANGAS', 'MUSIQUE'],
      isAuthenticated: false,
    };
  }
}

export async function fetchPopularDecks(category?: string): Promise<Deck[]> {
  try {
    const query = category && category !== 'ALL' ? `?category=${category}` : '';
    const raw = await request<any[]>(`/home/decks/popular${query}`);
    return raw.map((d) => ({
      id: d.id,
      title: d.title,
      slug: d.slug,
      category: d.category as DeckCategory,
      description: d.description || '',
      itemsCount: d.items_count || 10,
      playCount: d.play_count || 120,
      rating: 4.8,
      badge: d.is_official ? 'OFFICIEL' : undefined,
    }));
  } catch (err) {
    console.warn('Fallback popular decks:', err);
    return category && category !== 'ALL'
      ? mockDecks.filter((d) => d.category === category)
      : mockDecks;
  }
}

export async function launchQuickGame(deckId?: string): Promise<any> {
  const query = deckId ? `?deck_id=${deckId}` : '';
  return request<any>(`/home/quick-game${query}`, { method: 'POST' });
}

// AI Deck Creation
export async function fetchInspirationSuggestions(): Promise<string[]> {
  try {
    return await request<string[]>('/creation-ai/suggestions');
  } catch {
    return [
      'Films de SF des années 90',
      'Légendes du Football Moderne',
      'Animés Culte & Shōnen',
      'Grandes Batailles de l\'Histoire',
      'Monuments & Merveilles du Monde',
      'Rock & Légendes de la Musique',
    ];
  }
}

export async function generateAiDeck(payload: {
  prompt: string;
  category?: string;
  itemsCount?: number;
}): Promise<Deck> {
  const data = await request<any>('/creation-ai/generate', {
    method: 'POST',
    body: JSON.stringify({
      prompt: payload.prompt,
      category: payload.category || 'POP_CULTURE',
      items_count: payload.itemsCount || 10,
    }),
  });

  return {
    id: data.id,
    title: data.title,
    slug: data.slug,
    category: data.category as DeckCategory,
    description: data.description,
    itemsCount: data.items?.length || 10,
    badge: 'NOUVEAU',
    author: 'IA Gemini',
    items: (data.items || []).map((item: any) => ({
      id: item.id,
      name: item.name,
      clue1: item.clue_1,
      clue2: item.clue_2,
      clue3: item.clue_3,
      score: item.base_score,
      rarity: item.rarity?.toLowerCase() || 'common',
      category: item.category,
    })),
  };
}

// Live Auction REST & WS

export async function createSessionApi(payload: {
  deck_id: string;
  mode?: 'LOCAL_PASS_AND_PLAY' | 'ONLINE_MULTIPLAYER';
  player_names: string[];
  starting_budget?: number;
  total_rounds?: number;
  timer_seconds?: number;
}): Promise<any> {
  return request<any>('/auction/sessions', {
    method: 'POST',
    body: JSON.stringify({
      deck_id: payload.deck_id,
      mode: payload.mode || 'ONLINE_MULTIPLAYER',
      player_names: payload.player_names,
      starting_budget: payload.starting_budget ?? 1000,
      total_rounds: payload.total_rounds ?? 5,
      timer_seconds: payload.timer_seconds ?? 15,
    }),
  });
}

export async function joinSessionApi(code: string): Promise<any> {
  return request<any>('/auction/sessions/join', {
    method: 'POST',
    body: JSON.stringify({ code: code.trim().toUpperCase() }),
  });
}

export async function startSessionApi(sessionId: string): Promise<any> {
  return request<any>(`/auction/sessions/${sessionId}/start`, {
    method: 'POST',
  });
}

export async function fetchAuctionLiveState(sessionId: string): Promise<any> {
  return request<any>(`/auction/sessions/${sessionId}/live-state`);
}

export async function submitBidApi(
  sessionId: string,
  playerId: string,
  amount: number,
  isPass: boolean = false
): Promise<any> {
  return request<any>(`/auction/sessions/${sessionId}/bid`, {
    method: 'POST',
    body: JSON.stringify({
      player_id: playerId,
      amount: amount,
      is_pass: isPass,
    }),
  });
}

export async function advanceAuctionApi(
  sessionId: string,
  expectedRound: number,
  expectedClue: number
): Promise<any> {
  return request<any>(
    `/auction/sessions/${sessionId}/advance?expected_round=${expectedRound}&expected_clue=${expectedClue}`,
    { method: 'POST' }
  );
}

// Results
export async function fetchGameResults(sessionId: string): Promise<GameResultsResponse> {
  return request<GameResultsResponse>(`/results/sessions/${sessionId}/results`);
}

// Shop & Token Economy
export async function fetchShopPacks(): Promise<ShopPack[]> {
  try {
    const raw = await request<any[]>('/shop/packs');
    return raw.map((p) => ({
      id: p.id,
      sku: p.sku,
      tokens: p.tokens_amount,
      price: `${(p.price_cents / 100).toFixed(2).replace('.', ',')} €`,
      priceCents: p.price_cents,
      isPopular: p.is_best_value,
      badge: p.badge_text,
    }));
  } catch (err) {
    console.warn('Fallback shop packs:', err);
    return mockShopPacks;
  }
}

export async function claimRewardedAdApi(rewardToken?: string): Promise<any> {
  const token = rewardToken || `ad_token_${Date.now()}_${Math.random().toString(36).substring(2)}`;
  return request<any>('/shop/claim-rewarded-ad', {
    method: 'POST',
    body: JSON.stringify({
      ad_network: 'admob',
      reward_token: token,
    }),
  });
}

export async function verifyIapApi(packSku: string, transactionId: string): Promise<any> {
  return request<any>('/shop/verify-iap', {
    method: 'POST',
    body: JSON.stringify({
      pack_sku: packSku,
      platform: 'apple',
      receipt_data: 'mock_receipt_payload',
      transaction_id: transactionId,
    }),
  });
}

export async function fetchTransactionHistory(): Promise<Transaction[]> {
  try {
    const raw = await request<any[]>('/shop/transactions');
    return raw.map((tx) => ({
      id: tx.id,
      title: tx.metadata_json?.deck_title
        ? `Génération IA : ${tx.metadata_json.deck_title}`
        : tx.transaction_type === 'REWARDED_AD'
        ? 'Vidéo Publicitaire Récompensée'
        : tx.transaction_type === 'INITIAL_GIFT'
        ? 'Cadeau de Bienvenue'
        : 'Transaction',
      date: new Date(tx.created_at).toLocaleDateString('fr-FR', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      }),
      amount: tx.amount,
      type: tx.amount >= 0 ? 'gain' : 'spend',
    }));
  } catch {
    return mockInitialTransactions;
  }
}

// WebSocket Connection Helper with Single-Use Ticket, Auto-Reconnect & Exponential Backoff
export function connectAuctionWs(
  sessionId: string,
  callbacks: {
    onOpen?: () => void;
    onMessage: (msg: any) => void;
    onError?: (err: any) => void;
    onClose?: (event: CloseEvent) => void;
  }
): () => void {
  const wsBaseUrl = API_BASE_URL.replace(/^http/i, 'ws');

  let ws: WebSocket | null = null;
  let pingTimer: any = null;
  let reconnectTimer: any = null;
  let retryCount = 0;
  let isClosedManually = false;
  let hasConnectedOnce = false;

  function scheduleReconnect() {
    if (isClosedManually) return;
    const delay = Math.min(1000 * Math.pow(2, retryCount), 10000); // 1s, 2s, 4s, 8s, max 10s
    retryCount++;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      if (!isClosedManually) {
        void connect();
      }
    }, delay);
  }

  async function connect() {
    if (isClosedManually) return;
    try {
      const ticketData = await request<{ ticket: string }>('/auction/ws-ticket', {
        method: 'POST',
      });
      if (isClosedManually) return;

      const wsUrl = `${wsBaseUrl}/auction/ws/${sessionId}?ticket=${encodeURIComponent(ticketData.ticket)}`;
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        retryCount = 0;
        callbacks.onOpen?.();

        // En cas de reconnexion après coupure, émettre une demande de synchronisation d'état au serveur
        if (hasConnectedOnce) {
          try {
            ws?.send(JSON.stringify({ action: 'sync' }));
          } catch {
            // ignore
          }
        }
        hasConnectedOnce = true;

        // Keep-alive heartbeat ping every 25 seconds
        if (pingTimer) clearInterval(pingTimer);
        pingTimer = setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'ping' }));
          }
        }, 25000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          callbacks.onMessage(data);
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = (err) => {
        callbacks.onError?.(err);
      };

      ws.onclose = (event) => {
        if (pingTimer) clearInterval(pingTimer);
        callbacks.onClose?.(event);
        if (!isClosedManually) {
          scheduleReconnect();
        }
      };
    } catch (e) {
      callbacks.onError?.(e);
      if (!isClosedManually) {
        scheduleReconnect();
      }
    }
  }

  void connect();

  return () => {
    isClosedManually = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (pingTimer) clearInterval(pingTimer);
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      ws.close();
    }
  };
}

// Fallback Mock Data
export const mockDecks: Deck[] = [
  {
    id: 'deck-1',
    title: 'Légendes du Football 2000s',
    category: 'SPORT',
    author: 'Alexandre G.',
    itemsCount: 10,
    rating: 4.9,
    playCount: 1420,
    badge: 'POPULAIRE',
    description: "De Zidane à Ronaldinho, testez votre flair sur l'âge d'or du football.",
  },
  {
    id: 'deck-2',
    title: "Chefs-d'œuvre du Studio Ghibli",
    category: 'MANGAS',
    author: 'MiyazakiFan',
    itemsCount: 10,
    rating: 4.8,
    playCount: 980,
    badge: 'COUP DE CŒUR',
    description: 'Voyage de Chihiro, Mononoké, Totoro... Retrouvez les films et personnages cultes.',
  },
  {
    id: 'deck-3',
    title: 'Grands Braquages du Cinéma',
    category: 'CINEMA',
    author: 'IA Gemini',
    itemsCount: 10,
    rating: 4.7,
    playCount: 2310,
    badge: 'IA GÉNÉRÉ',
    description: 'Heat, Ocean\'s Eleven, La Casa de Papel... Démasquez les plans parfaits.',
  },
  {
    id: 'deck-4',
    title: 'Mystères & Conquêtes de l\'Histoire',
    category: 'HISTOIRE',
    author: 'Clio99',
    itemsCount: 10,
    rating: 4.6,
    playCount: 760,
    description: 'De l\'Égypte antique à la Guerre Froide, devinez les tournants du monde.',
  },
  {
    id: 'deck-5',
    title: 'Pop Culture & Séries 2010s',
    category: 'POP_CULTURE',
    author: 'Thomas R.',
    itemsCount: 10,
    rating: 4.9,
    playCount: 3120,
    badge: 'TENDANCE',
    description: 'Stranger Things, Game of Thrones, Marvel Cinematic Universe et mèmes viraux.',
  },
  {
    id: 'deck-6',
    title: 'Anthologie Rock & Hip-Hop 90s',
    category: 'MUSIQUE',
    author: 'GrooveMaster',
    itemsCount: 10,
    rating: 4.7,
    playCount: 650,
    description: 'Nirvana, Tupac, Daft Punk, Oasis... Les hymnes qui ont marqué une décennie.',
  },
];

export const mockShopPacks: ShopPack[] = [
  {
    id: 'pack-starter',
    tokens: 5,
    price: '0,99 €',
    badge: 'DÉMARRAGE',
  },
  {
    id: 'pack-pro',
    tokens: 15,
    bonusTokens: 3,
    price: '2,49 €',
    isPopular: true,
    badge: 'MEILLEURE VALEUR',
  },
  {
    id: 'pack-master',
    tokens: 50,
    bonusTokens: 15,
    price: '6,99 €',
    badge: 'PACK ÉLITE',
  },
];

export const mockInitialTransactions: Transaction[] = [
  {
    id: 'tx-1',
    title: 'Vidéo Publicitaire Récompensée',
    date: 'Aujourd\'hui, 14:22',
    amount: 1,
    type: 'gain',
  },
  {
    id: 'tx-2',
    title: 'Génération IA Deck Cinéma',
    date: 'Hier, 19:40',
    amount: -1,
    type: 'spend',
  },
  {
    id: 'tx-3',
    title: 'Pack Populaire (15 Jetons)',
    date: '05 Oct, 11:15',
    amount: 15,
    type: 'gain',
  },
  {
    id: 'tx-4',
    title: 'Cadeau de Bienvenue',
    date: '01 Oct, 09:00',
    amount: 3,
    type: 'gain',
  },
];

export const mockDeckItems: DeckItem[] = [
  {
    id: 'item-1',
    name: 'Zinédine Zidane',
    clue1: 'Numéro 10 emblématique et maître du contrôle orienté.',
    clue2: 'Auteur d\'un doublé légendaire de la tête en finale au Stade de France.',
    clue3: 'Célèbre pour une volée d\'anthologie à Glasgow avec le Real Madrid.',
    score: 96,
    rarity: 'legendary',
    category: 'SPORT',
  },
  {
    id: 'item-2',
    name: 'Le Voyage de Chihiro',
    clue1: 'Film d\'animation japonais récompensé d\'un Oscar historique en 2003.',
    clue2: 'Une jeune fille se retrouve piégée dans une station thermale pour esprits.',
    clue3: 'Ses parents sont métamorphosés en cochons après un festin suspect.',
    score: 88,
    rarity: 'epic',
    category: 'MANGAS',
  },
  {
    id: 'item-3',
    name: 'Inception',
    clue1: 'Thriller de science-fiction réalisé par Christopher Nolan.',
    clue2: 'Une équipe de voleurs s\'infiltre dans les rêves pour y implanter une idée.',
    clue3: 'Une toupie qui tourne sans jamais s\'arrêter laisse planer le doute.',
    score: 91,
    rarity: 'legendary',
    category: 'CINEMA',
  },
  {
    id: 'item-4',
    name: 'Pulp Fiction',
    clue1: 'Film culte des années 90 à la narration déconstruite en chapitres.',
    clue2: 'Une mallette lumineuse dont le contenu n\'est jamais révélé.',
    clue3: 'Une danse mémorable au Jack Rabbit Slim\'s sur Chuck Berry.',
    score: 84,
    rarity: 'rare',
    category: 'CINEMA',
  },
];
