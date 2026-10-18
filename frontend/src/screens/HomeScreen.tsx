import React, { useState, useEffect } from 'react';
import {
  Globe,
  Smartphone,
  Sparkles,
  Users,
  Star,
  Layers,
  Flame,
  Copy,
  Check,
  X,
  Play,
  ArrowRight,
} from 'lucide-react';
import { DeckCategory, ScreenId, Deck } from '../models';
import { TopBar } from '../widgets/TopBar';
import { PillChip } from '../widgets/PillChip';
import { Button3D } from '../widgets/Button3D';
import {
  fetchPopularDecks,
  mockDecks,
  createSessionApi,
  joinSessionApi,
} from '../services/api';

export interface HomeScreenProps {
  tokensCount: number;
  playerName?: string;
  onNavigate: (screen: ScreenId) => void;
  onStartGame?: (deck: Deck) => void;
  onStartLocalGame: (deck: Deck, playerNames: string[]) => void;
  onStartOnlineGame: (deck: Deck, sessionId?: string, roomCode?: string) => void;
}

const generateFallbackRoomCode = (): string => Math.random().toString(36).substring(2, 8).toUpperCase();
const generateFallbackRoomId = (): string => `online-room-${Date.now()}`;

export const HomeScreen: React.FC<HomeScreenProps> = ({
  tokensCount,
  playerName = 'Alex',
  onNavigate,
  onStartLocalGame,
  onStartOnlineGame,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<DeckCategory>('ALL');
  const [decks, setDecks] = useState<Deck[]>(mockDecks);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Modals state
  const [showLocalModal, setShowLocalModal] = useState<boolean>(false);
  const [showOnlineModal, setShowOnlineModal] = useState<boolean>(false);
  const [selectedDeckForGame, setSelectedDeckForGame] = useState<Deck>(mockDecks[0]);

  // Local Pass & Play Config
  const [playerCount, setPlayerCount] = useState<number>(3);
  const [playerNames, setPlayerNames] = useState<string[]>([playerName, 'Sophie', 'Lucas', 'Thomas']);

  // Online Multiplayer Config
  const [onlineTab, setOnlineTab] = useState<'create' | 'join'>('create');
  const [roomCodeInput, setRoomCodeInput] = useState<string>('');
  const [isSubmittingOnline, setIsSubmittingOnline] = useState<boolean>(false);
  const [onlineError, setOnlineError] = useState<string | null>(null);
  const [createdRoom, setCreatedRoom] = useState<{ id: string; code: string } | null>(null);
  const [copiedCode, setCopiedCode] = useState<boolean>(false);

  const categories: { id: DeckCategory; label: string; icon: string }[] = [
    { id: 'ALL', label: 'Tous', icon: '🌟' },
    { id: 'POP_CULTURE', label: 'Pop Culture', icon: '⚡' },
    { id: 'CINEMA', label: 'Cinéma', icon: '🎬' },
    { id: 'SPORT', label: 'Sport', icon: '⚽' },
    { id: 'HISTOIRE', label: 'Histoire', icon: '🏛️' },
    { id: 'MANGAS', label: 'Mangas', icon: '🎌' },
    { id: 'MUSIQUE', label: 'Musique', icon: '🎵' },
  ];

  useEffect(() => {
    let isCancelled = false;
    async function loadDecks() {
      setIsLoading(true);
      try {
        const remoteDecks = await fetchPopularDecks(selectedCategory === 'ALL' ? undefined : selectedCategory);
        if (!isCancelled && remoteDecks && remoteDecks.length > 0) {
          setDecks(remoteDecks);
          setSelectedDeckForGame(remoteDecks[0]);
        }
      } catch {
        if (!isCancelled) {
          const fallback =
            selectedCategory === 'ALL'
              ? mockDecks
              : mockDecks.filter((d) => d.category === selectedCategory);
          setDecks(fallback);
          if (fallback.length > 0) setSelectedDeckForGame(fallback[0]);
        }
      } finally {
        if (!isCancelled) setIsLoading(false);
      }
    }
    loadDecks();
    return () => {
      isCancelled = true;
    };
  }, [selectedCategory]);

  // Open Local Pass & Play modal
  const handleOpenLocalModal = (deck?: Deck) => {
    if (deck) setSelectedDeckForGame(deck);
    setShowLocalModal(true);
  };

  // Open Online Multiplayer modal
  const handleOpenOnlineModal = (deck?: Deck) => {
    if (deck) setSelectedDeckForGame(deck);
    setOnlineError(null);
    setCreatedRoom(null);
    setRoomCodeInput('');
    setShowOnlineModal(true);
  };

  // Launch Local Game
  const handleConfirmLocalGame = () => {
    const activeNames = playerNames.slice(0, playerCount).map((n, idx) => n.trim() || `Joueur ${idx + 1}`);
    setShowLocalModal(false);
    onStartLocalGame(selectedDeckForGame, activeNames);
  };

  // Create Online Session
  const handleCreateOnlineRoom = async () => {
    setIsSubmittingOnline(true);
    setOnlineError(null);
    try {
      const res = await createSessionApi({
        deck_id: selectedDeckForGame.id.startsWith('deck-') ? '00000000-0000-0000-0000-000000000001' : selectedDeckForGame.id,
        mode: 'ONLINE_MULTIPLAYER',
        player_names: [playerName],
        starting_budget: 1000,
        total_rounds: 5,
        timer_seconds: 15,
      });

      if (res && res.id && res.code) {
        setCreatedRoom({ id: res.id, code: res.code });
      } else {
        // Fallback simulated room code
        setCreatedRoom({ id: 'online-temp-id', code: generateFallbackRoomCode() });
      }
    } catch (err: any) {
      console.warn('Erreur création salon en ligne:', err);
      // Fallback gracieux en environnement de test
      setCreatedRoom({ id: generateFallbackRoomId(), code: generateFallbackRoomCode() });
    } finally {
      setIsSubmittingOnline(false);
    }
  };

  // Start the created online room
  const handleLaunchCreatedRoom = () => {
    if (!createdRoom) return;
    setShowOnlineModal(false);
    onStartOnlineGame(selectedDeckForGame, createdRoom.id, createdRoom.code);
  };

  // Join Online Session by code
  const handleJoinOnlineRoom = async () => {
    const code = roomCodeInput.trim().toUpperCase();
    if (!code) {
      setOnlineError('Veuillez entrer un code de salon');
      return;
    }
    setIsSubmittingOnline(true);
    setOnlineError(null);
    try {
      const res = await joinSessionApi(code);
      setShowOnlineModal(false);
      onStartOnlineGame(selectedDeckForGame, res.id, res.code || code);
    } catch (err: any) {
      setOnlineError(err.message || 'Code de salon introuvable ou salon complet');
    } finally {
      setIsSubmittingOnline(false);
    }
  };

  const handleCopyCode = (code: string) => {
    navigator.clipboard?.writeText(code);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
  };

  const filteredDecks = decks;

  return (
    <div style={{ paddingBottom: 24, display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* TopBar */}
      <TopBar
        tokensCount={tokensCount}
        onTokensClick={() => onNavigate('shop')}
        playerName={playerName}
        playerLevel={12}
      />

      {/* Main Content Area */}
      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        
        {/* HERO CARD : SÉPARATION EXPLICITE DES DEUX MODES DE JEU */}
        <div
          style={{
            background: 'linear-gradient(135deg, #1E1B4B 0%, #312E81 55%, #3730A3 100%)',
            borderRadius: 24,
            padding: '22px 18px',
            color: '#FFFFFF',
            border: '3px solid #0F172A',
            boxShadow: '0 8px 0 #0F172A',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          {/* Subtle background glow */}
          <div
            style={{
              position: 'absolute',
              top: -40,
              right: -40,
              width: 140,
              height: 140,
              borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(99,102,241,0.3) 0%, rgba(99,102,241,0) 70%)',
              pointerEvents: 'none',
            }}
          />

          <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span
                style={{
                  backgroundColor: '#4F46E5',
                  color: '#FFFFFF',
                  fontSize: '11px',
                  fontWeight: 900,
                  padding: '4px 10px',
                  borderRadius: 12,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  letterSpacing: '0.04em',
                }}
              >
                <Flame size={13} fill="#F59E0B" stroke="#F59E0B" /> DRAFT & ENCHÈRES LIVE
              </span>
              <span style={{ fontSize: '11px', fontWeight: 800, color: '#A5B4FC' }}>
                Thème : {selectedDeckForGame?.title?.slice(0, 18) || 'Pop Culture'}...
              </span>
            </div>

            <div>
              <h2 style={{ fontSize: '22px', fontWeight: 900, margin: '0 0 6px', lineHeight: 1.25 }}>
                Lancez une Partie
              </h2>
              <p style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: '#C7D2FE', lineHeight: 1.4 }}>
                Choisissez votre façon de jouer : tour par tour sur ce téléphone ou multijoueur en ligne en temps réel !
              </p>
            </div>

            {/* LES DEUX CHOIX EXPLICITES */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
              
              {/* Choix 1 : Multijoueur en Ligne */}
              <button
                onClick={() => handleOpenOnlineModal(selectedDeckForGame)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 14px',
                  borderRadius: 16,
                  backgroundColor: '#4F46E5',
                  border: '2px solid #6366F1',
                  boxShadow: '0 4px 0 #312E81',
                  color: '#FFFFFF',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'transform 0.1s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 12,
                      backgroundColor: '#3730A3',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Globe size={22} color="#A5B4FC" />
                  </div>
                  <div>
                    <div style={{ fontSize: '15px', fontWeight: 900, display: 'flex', alignItems: 'center', gap: 6 }}>
                      🌐 Multijoueur en Ligne
                      <span style={{ fontSize: '10px', backgroundColor: '#10B981', color: '#FFFFFF', padding: '1px 6px', borderRadius: 8, fontWeight: 800 }}>
                        LIVE
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', fontWeight: 600, color: '#C7D2FE' }}>
                      Créer un salon ou rejoindre avec code
                    </div>
                  </div>
                </div>
                <ArrowRight size={18} color="#C7D2FE" />
              </button>

              {/* Choix 2 : Mode Soirée Locale (Pass & Play) */}
              <button
                onClick={() => handleOpenLocalModal(selectedDeckForGame)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 14px',
                  borderRadius: 16,
                  backgroundColor: '#059669',
                  border: '2px solid #10B981',
                  boxShadow: '0 4px 0 #064E3B',
                  color: '#FFFFFF',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'transform 0.1s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 12,
                      backgroundColor: '#047857',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Smartphone size={22} color="#A7F3D0" />
                  </div>
                  <div>
                    <div style={{ fontSize: '15px', fontWeight: 900, display: 'flex', alignItems: 'center', gap: 6 }}>
                      📱 Mode Soirée Locale
                      <span style={{ fontSize: '10px', backgroundColor: '#F59E0B', color: '#FFFFFF', padding: '1px 6px', borderRadius: 8, fontWeight: 800 }}>
                        PASS & PLAY
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', fontWeight: 600, color: '#A7F3D0' }}>
                      2 à 4 joueurs • Tour par tour sur ce téléphone
                    </div>
                  </div>
                </div>
                <ArrowRight size={18} color="#A7F3D0" />
              </button>

            </div>
          </div>
        </div>

        {/* AI Generator Teaser Banner */}
        <div
          style={{
            backgroundColor: '#FFFBEB',
            borderRadius: 20,
            border: '2px solid #FCD34D',
            boxShadow: '0 3px 0 #D97706',
            padding: '14px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div
              style={{
                width: 42,
                height: 42,
                borderRadius: 14,
                backgroundColor: '#F59E0B',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#FFFFFF',
                boxShadow: '0 2px 0 #B45309',
              }}
            >
              <Sparkles size={22} />
            </div>
            <div>
              <div style={{ fontSize: '15px', fontWeight: 900, color: '#78350F' }}>
                Créateur de Thèmes IA
              </div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#B45309' }}>
                Générez 10 cartes inédites sur mesure
              </div>
            </div>
          </div>
          <Button3D
            variant="secondary"
            size="sm"
            onClick={() => onNavigate('creation')}
          >
            Créer ⚡1
          </Button3D>
        </div>

        {/* Categories Chips Slider */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <h3 style={{ fontSize: '17px', fontWeight: 900, color: '#1E1B4B', margin: 0 }}>
              Catégories
            </h3>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#6366F1' }}>
              {filteredDecks.length} thèmes
            </span>
          </div>

          <div
            style={{
              display: 'flex',
              gap: 8,
              overflowX: 'auto',
              paddingBottom: 6,
              scrollbarWidth: 'none',
            }}
          >
            {categories.map((cat) => (
              <PillChip
                key={cat.id}
                label={`${cat.icon} ${cat.label}`}
                isActive={selectedCategory === cat.id}
                onClick={() => setSelectedCategory(cat.id)}
              />
            ))}
          </div>
        </div>

        {/* Popular Decks Grid */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <h3 style={{ fontSize: '17px', fontWeight: 900, color: '#1E1B4B', margin: 0 }}>
              Decks Populaires
            </h3>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#64748B' }}>
              {isLoading ? 'Chargement...' : 'Filtre actif'}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {filteredDecks.map((deck) => (
              <div
                key={deck.id}
                style={{
                  backgroundColor: '#FFFFFF',
                  borderRadius: 20,
                  padding: '16px',
                  border: '2px solid #E2E8F0',
                  boxShadow: '0 3px 0 #CBD5E1',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                  transition: 'transform 0.1s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 800,
                          backgroundColor: '#EEF2FF',
                          color: '#4F46E5',
                          padding: '2px 8px',
                          borderRadius: 8,
                        }}
                      >
                        {deck.category}
                      </span>
                      {deck.badge && (
                        <span
                          style={{
                            fontSize: '11px',
                            fontWeight: 800,
                            backgroundColor: '#FEF3C7',
                            color: '#B45309',
                            padding: '2px 8px',
                            borderRadius: 8,
                          }}
                        >
                          {deck.badge}
                        </span>
                      )}
                    </div>
                    <h4 style={{ fontSize: '16px', fontWeight: 900, color: '#1E1B4B', margin: '4px 0 0' }}>
                      {deck.title}
                    </h4>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#F59E0B', fontSize: '13px', fontWeight: 800 }}>
                    <Star size={15} fill="#F59E0B" />
                    {deck.rating || 4.8}
                  </div>
                </div>

                <p style={{ margin: 0, fontSize: '13px', color: '#64748B', lineHeight: 1.4, fontWeight: 500 }}>
                  {deck.description}
                </p>

                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    paddingTop: 8,
                    borderTop: '1px solid #F1F5F9',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: '12px', color: '#64748B', fontWeight: 700 }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Layers size={14} /> {deck.itemsCount} cartes
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Users size={14} /> {deck.playCount || 100} parties
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button3D
                      variant="success"
                      size="sm"
                      onClick={() => handleOpenLocalModal(deck)}
                    >
                      📱 Pass & Play
                    </Button3D>
                    <Button3D
                      variant="primary"
                      size="sm"
                      onClick={() => handleOpenOnlineModal(deck)}
                    >
                      🌐 En Ligne
                    </Button3D>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* ========================================================================= */}
      {/* MODAL 1 : MODE SOIRÉE LOCALE (PASS & PLAY) */}
      {/* ========================================================================= */}
      {showLocalModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: 16,
          }}
        >
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: 24,
              border: '3px solid #10B981',
              boxShadow: '0 12px 30px rgba(0,0,0,0.3)',
              width: '100%',
              maxWidth: 380,
              padding: 20,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: '20px' }}>📱</span>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 900, color: '#064E3B' }}>
                    Soirée Pass & Play
                  </h3>
                </div>
                <p style={{ margin: '4px 0 0', fontSize: '12px', fontWeight: 600, color: '#059669' }}>
                  Un seul téléphone • Tour par tour avec chrono
                </p>
              </div>
              <button
                onClick={() => setShowLocalModal(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#94A3B8',
                  padding: 4,
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Deck Selected Banner */}
            <div
              style={{
                backgroundColor: '#F0FDF4',
                border: '1px solid #BBF7D0',
                borderRadius: 14,
                padding: '10px 12px',
                fontSize: '12px',
                fontWeight: 700,
                color: '#166534',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span>Deck : <strong>{selectedDeckForGame.title}</strong></span>
              <span style={{ backgroundColor: '#DCFCE7', padding: '2px 8px', borderRadius: 6, fontSize: '11px' }}>
                5 manches
              </span>
            </div>

            {/* Player Count Selector */}
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 800, color: '#1E293B', marginBottom: 8 }}>
                Nombre de Joueurs
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                {[2, 3, 4].map((count) => (
                  <button
                    key={count}
                    type="button"
                    onClick={() => setPlayerCount(count)}
                    style={{
                      padding: '10px 0',
                      borderRadius: 12,
                      border: playerCount === count ? '2px solid #059669' : '2px solid #E2E8F0',
                      backgroundColor: playerCount === count ? '#ECFDF5' : '#FFFFFF',
                      color: playerCount === count ? '#065F46' : '#64748B',
                      fontWeight: 900,
                      fontSize: '14px',
                      cursor: 'pointer',
                    }}
                  >
                    {count} Joueurs
                  </button>
                ))}
              </div>
            </div>

            {/* Player Names Inputs */}
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 800, color: '#1E293B', marginBottom: 8 }}>
                Prénoms des Joueurs
              </label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {Array.from({ length: playerCount }).map((_, idx) => {
                  const colors = ['#3B82F6', '#EC4899', '#8B5CF6', '#F59E0B'];
                  return (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        backgroundColor: '#F8FAFC',
                        border: '1px solid #E2E8F0',
                        borderRadius: 12,
                        padding: '6px 12px',
                      }}
                    >
                      <div
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: '50%',
                          backgroundColor: colors[idx % colors.length],
                          color: '#FFFFFF',
                          fontSize: '12px',
                          fontWeight: 900,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        J{idx + 1}
                      </div>
                      <input
                        type="text"
                        value={playerNames[idx] || ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          setPlayerNames((prev) => {
                            const copy = [...prev];
                            copy[idx] = val;
                            return copy;
                          });
                        }}
                        placeholder={`Joueur ${idx + 1}`}
                        style={{
                          flex: 1,
                          border: 'none',
                          background: 'transparent',
                          fontSize: '14px',
                          fontWeight: 700,
                          color: '#1E293B',
                          outline: 'none',
                        }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Action Launch */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 6 }}>
              <Button3D
                variant="success"
                size="lg"
                fullWidth
                icon={<Play size={18} fill="#FFFFFF" />}
                onClick={handleConfirmLocalGame}
              >
                Démarrer la Soirée ({playerCount}J)
              </Button3D>
              <button
                onClick={() => setShowLocalModal(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#64748B',
                  fontWeight: 700,
                  fontSize: '13px',
                  cursor: 'pointer',
                  padding: '6px 0',
                }}
              >
                Annuler
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 2 : MULTIJOUEUR EN LIGNE (SALONS & CODES DE SESSION) */}
      {/* ========================================================================= */}
      {showOnlineModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: 16,
          }}
        >
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: 24,
              border: '3px solid #6366F1',
              boxShadow: '0 12px 30px rgba(0,0,0,0.3)',
              width: '100%',
              maxWidth: 390,
              padding: 20,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
              maxHeight: '90vh',
              overflowY: 'auto',
            }}
          >
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: '20px' }}>🌐</span>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 900, color: '#1E1B4B' }}>
                    Multijoueur en Ligne
                  </h3>
                </div>
                <p style={{ margin: '4px 0 0', fontSize: '12px', fontWeight: 600, color: '#6366F1' }}>
                  Enchères simultanées en direct via WebSocket
                </p>
              </div>
              <button
                onClick={() => setShowOnlineModal(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#94A3B8',
                  padding: 4,
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Tab Switcher */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                backgroundColor: '#F1F5F9',
                borderRadius: 14,
                padding: 4,
                gap: 4,
              }}
            >
              <button
                type="button"
                onClick={() => {
                  setOnlineTab('create');
                  setOnlineError(null);
                }}
                style={{
                  padding: '8px 0',
                  borderRadius: 10,
                  border: 'none',
                  backgroundColor: onlineTab === 'create' ? '#FFFFFF' : 'transparent',
                  color: onlineTab === 'create' ? '#312E81' : '#64748B',
                  fontWeight: 900,
                  fontSize: '13px',
                  boxShadow: onlineTab === 'create' ? '0 2px 4px rgba(0,0,0,0.06)' : 'none',
                  cursor: 'pointer',
                }}
              >
                Créer un Salon
              </button>
              <button
                type="button"
                onClick={() => {
                  setOnlineTab('join');
                  setOnlineError(null);
                }}
                style={{
                  padding: '8px 0',
                  borderRadius: 10,
                  border: 'none',
                  backgroundColor: onlineTab === 'join' ? '#FFFFFF' : 'transparent',
                  color: onlineTab === 'join' ? '#312E81' : '#64748B',
                  fontWeight: 900,
                  fontSize: '13px',
                  boxShadow: onlineTab === 'join' ? '0 2px 4px rgba(0,0,0,0.06)' : 'none',
                  cursor: 'pointer',
                }}
              >
                Rejoindre par Code
              </button>
            </div>

            {/* Error banner */}
            {onlineError && (
              <div
                style={{
                  backgroundColor: '#FEE2E2',
                  border: '1px solid #FCA5A5',
                  borderRadius: 12,
                  padding: '8px 12px',
                  color: '#991B1B',
                  fontSize: '12px',
                  fontWeight: 700,
                }}
              >
                {onlineError}
              </div>
            )}

            {/* TAB 1 : CRÉER UN SALON */}
            {onlineTab === 'create' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div
                  style={{
                    backgroundColor: '#EEF2FF',
                    border: '1px solid #C7D2FE',
                    borderRadius: 14,
                    padding: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                  }}
                >
                  <div style={{ fontSize: '11px', fontWeight: 800, color: '#4F46E5', textTransform: 'uppercase' }}>
                    Thème sélectionné
                  </div>
                  <div style={{ fontSize: '15px', fontWeight: 900, color: '#1E1B4B' }}>
                    {selectedDeckForGame.title}
                  </div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#6366F1' }}>
                    5 manches • Budget initial : $1000 • Hôte : {playerName}
                  </div>
                </div>

                {createdRoom ? (
                  <div
                    style={{
                      backgroundColor: '#ECFDF5',
                      border: '2px solid #10B981',
                      borderRadius: 16,
                      padding: '14px',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: 10,
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ fontSize: '12px', fontWeight: 800, color: '#047857', textTransform: 'uppercase' }}>
                      🎉 Salon Prêt ! Partagez le code :
                    </div>
                    <div
                      style={{
                        fontSize: '32px',
                        fontWeight: 900,
                        letterSpacing: '0.15em',
                        color: '#065F46',
                        fontFamily: 'monospace',
                        padding: '6px 16px',
                        backgroundColor: '#FFFFFF',
                        borderRadius: 12,
                        border: '2px dashed #059669',
                      }}
                    >
                      {createdRoom.code}
                    </div>

                    <button
                      onClick={() => handleCopyCode(createdRoom.code)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        backgroundColor: '#FFFFFF',
                        border: '1px solid #A7F3D0',
                        borderRadius: 8,
                        padding: '6px 12px',
                        fontSize: '12px',
                        fontWeight: 800,
                        color: '#047857',
                        cursor: 'pointer',
                      }}
                    >
                      {copiedCode ? <Check size={14} color="#10B981" /> : <Copy size={14} />}
                      {copiedCode ? 'Copié !' : 'Copier le code'}
                    </button>

                    <Button3D
                      variant="primary"
                      size="md"
                      fullWidth
                      icon={<Play size={18} fill="#FFFFFF" />}
                      onClick={handleLaunchCreatedRoom}
                    >
                      Lancer la Salle d'Enchères
                    </Button3D>
                  </div>
                ) : (
                  <Button3D
                    variant="primary"
                    size="lg"
                    fullWidth
                    disabled={isSubmittingOnline}
                    onClick={handleCreateOnlineRoom}
                  >
                    {isSubmittingOnline ? 'Création en cours...' : 'Créer le Salon'}
                  </Button3D>
                )}
              </div>
            )}

            {/* TAB 2 : REJOINDRE AVEC CODE */}
            {onlineTab === 'join' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 800, color: '#1E293B', marginBottom: 6 }}>
                    Code de Session (6 lettres)
                  </label>
                  <input
                    type="text"
                    maxLength={10}
                    value={roomCodeInput}
                    onChange={(e) => setRoomCodeInput(e.target.value.toUpperCase())}
                    placeholder="Ex: DRAFT8"
                    style={{
                      width: '100%',
                      boxSizing: 'border-box',
                      padding: '12px 14px',
                      borderRadius: 14,
                      border: '2px solid #CBD5E1',
                      fontSize: '20px',
                      fontWeight: 900,
                      letterSpacing: '0.12em',
                      textAlign: 'center',
                      color: '#1E1B4B',
                      outline: 'none',
                      fontFamily: 'monospace',
                    }}
                  />
                  <span style={{ display: 'block', fontSize: '11px', color: '#64748B', marginTop: 4, textAlign: 'center' }}>
                    Demandez le code à l'hôte créateur du salon
                  </span>
                </div>

                <Button3D
                  variant="primary"
                  size="lg"
                  fullWidth
                  disabled={isSubmittingOnline || !roomCodeInput.trim()}
                  onClick={handleJoinOnlineRoom}
                >
                  {isSubmittingOnline ? 'Connexion...' : 'Rejoindre le Salon 🎮'}
                </Button3D>
              </div>
            )}

            <button
              onClick={() => setShowOnlineModal(false)}
              style={{
                background: 'none',
                border: 'none',
                color: '#64748B',
                fontWeight: 700,
                fontSize: '13px',
                cursor: 'pointer',
                textAlign: 'center',
              }}
            >
              Fermer
            </button>
          </div>
        </div>
      )}

    </div>
  );
};
