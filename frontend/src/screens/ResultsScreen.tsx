import React, { useEffect, useState } from 'react';
import confetti from 'canvas-confetti';
import { Trophy, RefreshCw, Home, Sparkles, Award } from 'lucide-react';
import { ScreenId, GameResultsResponse, DeckItem, LocalMatchResults } from '../models';
import { TopBar } from '../widgets/TopBar';
import { Button3D } from '../widgets/Button3D';
import { fetchGameResults } from '../services/api';

export interface ResultsScreenProps {
  tokensCount: number;
  sessionId?: string | null;
  localResults?: LocalMatchResults | null;
  onNavigate: (screen: ScreenId) => void;
  onPlayAgain: () => void;
}

interface RankedPlayer {
  rank: number;
  playerId: string;
  name: string;
  score: number;
  cardsWon: number;
  roi: string;
  cashLeft: string;
  spentCash: number;
  isWinner?: boolean;
}

export const ResultsScreen: React.FC<ResultsScreenProps> = ({
  tokensCount,
  sessionId,
  localResults,
  onNavigate,
  onPlayAgain,
}) => {
  const [playersRank, setPlayersRank] = useState<RankedPlayer[]>([]);
  const [draftedTeam, setDraftedTeam] = useState<DeckItem[]>([]);
  const [synergies, setSynergies] = useState<Array<{ name: string; bonus: number; description: string }>>([]);
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null);
  const [deckTitle, setDeckTitle] = useState<string>('Partie d\'Enchères');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  useEffect(() => {
    // 1. Priorité au résultat local de la Soirée Pass & Play qui vient d'être jouée
    if (localResults && localResults.podium && localResults.podium.length > 0) {
      setDeckTitle(localResults.deckTitle || 'Soirée Pass & Play');

      const mapped = localResults.podium.map((p) => {
        const comp = localResults.compositions?.find((c) => c.player_id === p.player_id);
        const cardsCount = comp?.items?.length || 0;
        const spent = comp?.spent_budget || 0;

        // Calcul du ROI réel : (score final - budget dépensé) / budget dépensé * 100
        let roiStr = '0%';
        if (spent > 0) {
          const roiPct = Math.round(((p.final_score - spent) / spent) * 100);
          roiStr = `${roiPct >= 0 ? '+' : ''}${roiPct}%`;
        } else if (p.final_score > 0) {
          roiStr = '+100%';
        }

        return {
          rank: p.rank,
          playerId: p.player_id,
          name: p.display_name,
          score: p.final_score,
          cardsWon: cardsCount,
          roi: roiStr,
          cashLeft: `$${p.remaining_budget}`,
          spentCash: spent,
          isWinner: p.rank === 1,
        };
      });

      setPlayersRank(mapped);

      // Sélectionner le vainqueur par défaut pour ses cartes et synergies
      const winnerComp = localResults.compositions?.[0];
      if (winnerComp) {
        setSelectedPlayerId(winnerComp.player_id);
        setDraftedTeam(
          (winnerComp.items || []).map((i: any) => ({
            id: i.id,
            name: i.name,
            clue1: '',
            clue2: '',
            clue3: '',
            score: i.base_score,
            rarity: (i.rarity?.toLowerCase() || 'common') as any,
            category: i.category || 'POP_CULTURE',
            winningBid: i.winning_bid,
            clueLevelWon: i.clue_level_won,
          }))
        );
        setSynergies(winnerComp.synergies_breakdown || []);
      }

      // Explosion de confetti pour le vainqueur réel
      try {
        confetti({
          particleCount: 80,
          spread: 70,
          origin: { y: 0.6 },
        });
      } catch {
        // ignore
      }
      return;
    }

    // 2. Si un sessionId en ligne est fourni, récupérer les résultats calculés par l'API
    if (sessionId) {
      setIsLoading(true);
      fetchGameResults(sessionId)
        .then((res: GameResultsResponse) => {
          if (res) {
            if (res.deck_title) setDeckTitle(res.deck_title);

            if (res.podium && res.podium.length > 0) {
              const mapped = res.podium.map((p) => {
                const comp = res.compositions?.find((c) => c.player_id === p.player_id);
                const cardsCount = comp?.items?.length || 0;
                const spent = comp?.spent_budget || 0;

                let roiStr = '0%';
                if (spent > 0) {
                  const roiPct = Math.round(((p.final_score - spent) / spent) * 100);
                  roiStr = `${roiPct >= 0 ? '+' : ''}${roiPct}%`;
                } else if (p.final_score > 0) {
                  roiStr = '+100%';
                }

                return {
                  rank: p.rank,
                  playerId: p.player_id,
                  name: p.display_name,
                  score: p.final_score,
                  cardsWon: cardsCount,
                  roi: roiStr,
                  cashLeft: `$${p.remaining_budget}`,
                  spentCash: spent,
                  isWinner: p.rank === 1,
                };
              });
              setPlayersRank(mapped);

              const winnerComp = res.compositions?.[0];
              if (winnerComp) {
                setSelectedPlayerId(winnerComp.player_id);
                setDraftedTeam(
                  (winnerComp.items || []).map((i: any) => ({
                    id: i.id,
                    name: i.name,
                    clue1: '',
                    clue2: '',
                    clue3: '',
                    score: i.base_score,
                    rarity: (i.rarity?.toLowerCase() || 'common') as any,
                    category: i.category || 'POP_CULTURE',
                    winningBid: i.winning_bid,
                    clueLevelWon: i.clue_level_won,
                  }))
                );
                setSynergies(winnerComp.synergies_breakdown || []);
              }

              try {
                confetti({
                  particleCount: 80,
                  spread: 70,
                  origin: { y: 0.6 },
                });
              } catch {
                // ignore
              }
            }
          }
        })
        .catch((err) => {
          console.warn('Erreur récupération résultats réels:', err);
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  }, [sessionId, localResults]);

  // Permet de switcher l'affichage de l'équipe et des synergies entre les différents joueurs du match
  const handleSelectPlayer = (player: RankedPlayer) => {
    setSelectedPlayerId(player.playerId);

    const comp = localResults?.compositions?.find((c) => c.player_id === player.playerId);
    if (comp) {
      setDraftedTeam(
        (comp.items || []).map((i: any) => ({
          id: i.id,
          name: i.name,
          clue1: '',
          clue2: '',
          clue3: '',
          score: i.base_score,
          rarity: (i.rarity?.toLowerCase() || 'common') as any,
          category: i.category || 'POP_CULTURE',
          winningBid: i.winning_bid,
          clueLevelWon: i.clue_level_won,
        }))
      );
      setSynergies(comp.synergies_breakdown || []);
    }
  };

  const winner = playersRank.find((p) => p.isWinner) || playersRank[0];
  const viewedPlayer = playersRank.find((p) => p.playerId === selectedPlayerId) || winner;

  return (
    <div style={{ paddingBottom: 30, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <TopBar
        title="Résultats du Match"
        tokensCount={tokensCount}
        onTokensClick={() => onNavigate('shop')}
      />

      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        
        {/* En cas de chargement */}
        {isLoading && (
          <div
            style={{
              padding: 24,
              textAlign: 'center',
              backgroundColor: '#FFFFFF',
              borderRadius: 20,
              border: '2px solid #E2E8F0',
              fontWeight: 800,
              color: '#4F46E5',
            }}
          >
            Calcul des synergies et du classement final...
          </div>
        )}

        {/* État vide si aucune partie jouée */}
        {!isLoading && playersRank.length === 0 && (
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: 24,
              padding: '32px 20px',
              textAlign: 'center',
              border: '2px solid #E2E8F0',
              boxShadow: '0 4px 0 #CBD5E1',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 14,
            }}
          >
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: '50%',
                backgroundColor: '#EEF2FF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#4F46E5',
              }}
            >
              <Trophy size={28} />
            </div>
            <div>
              <h3 style={{ fontSize: '18px', fontWeight: 900, color: '#1E1B4B', margin: '0 0 6px' }}>
                Aucune partie enregistrée
              </h3>
              <p style={{ margin: 0, fontSize: '13px', color: '#64748B', fontWeight: 600 }}>
                Terminez un match en mode Soirée Locale ou En Ligne pour afficher vos scores réels.
              </p>
            </div>
            <Button3D
              variant="primary"
              size="md"
              icon={<Home size={18} />}
              onClick={() => onNavigate('home')}
            >
              Retour à l'accueil
            </Button3D>
          </div>
        )}

        {/* HERO CARD DU VAINQUEUR RÉEL */}
        {winner && (
          <div
            style={{
              backgroundColor: '#1E1B4B',
              borderRadius: 24,
              padding: '22px 18px',
              color: '#FFFFFF',
              border: '3px solid #0F172A',
              boxShadow: '0 6px 0 #0F172A',
              textAlign: 'center',
              position: 'relative',
            }}
          >
            <div
              style={{
                width: 58,
                height: 58,
                borderRadius: '50%',
                backgroundColor: '#F59E0B',
                border: '3px solid #FFFFFF',
                boxShadow: '0 4px 0 #B45309',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 10px',
                color: '#FFFFFF',
              }}
            >
              <Trophy size={32} />
            </div>

            <span
              style={{
                backgroundColor: '#4F46E5',
                color: '#FFFFFF',
                fontSize: '11px',
                fontWeight: 900,
                padding: '3px 10px',
                borderRadius: 10,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              Vainqueur du Draft • {deckTitle}
            </span>

            <h2 style={{ fontSize: '24px', fontWeight: 900, margin: '8px 0 2px' }}>
              {winner.name}
            </h2>

            <div style={{ fontSize: '13px', fontWeight: 700, color: '#C7D2FE', marginBottom: 14 }}>
              Score Final Réel : <strong style={{ color: '#FCD34D', fontSize: '18px' }}>{winner.score} pts</strong>
            </div>

            {/* Métriques Réelles du Vainqueur */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
                gap: 8,
                backgroundColor: '#0F172A',
                padding: '10px 12px',
                borderRadius: 16,
              }}
            >
              <div>
                <div style={{ fontSize: '10px', color: '#94A3B8', fontWeight: 800, textTransform: 'uppercase' }}>
                  Cartes
                </div>
                <div style={{ fontSize: '15px', color: '#FFFFFF', fontWeight: 900 }}>
                  {winner.cardsWon}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '10px', color: '#94A3B8', fontWeight: 800, textTransform: 'uppercase' }}>
                  ROI Réel
                </div>
                <div style={{ fontSize: '15px', color: '#10B981', fontWeight: 900 }}>
                  {winner.roi}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '10px', color: '#94A3B8', fontWeight: 800, textTransform: 'uppercase' }}>
                  Cash Restant
                </div>
                <div style={{ fontSize: '15px', color: '#FCD34D', fontWeight: 900 }}>
                  {winner.cashLeft}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* CLASSEMENT FINAL & PODIUM DYNAMIQUE */}
        {playersRank.length > 0 && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <h3 style={{ fontSize: '17px', fontWeight: 900, color: '#1E1B4B', margin: 0 }}>
                Podium & Classement
              </h3>
              <span style={{ fontSize: '11px', color: '#64748B', fontWeight: 700 }}>
                Touchez un joueur pour voir son équipe
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {playersRank.map((p) => {
                const medal = p.rank === 1 ? '🥇' : p.rank === 2 ? '🥈' : p.rank === 3 ? '🥉' : '4️⃣';
                const isSelected = selectedPlayerId === p.playerId;

                return (
                  <div
                    key={p.playerId}
                    onClick={() => handleSelectPlayer(p)}
                    style={{
                      backgroundColor: p.isWinner ? '#FEF3C7' : '#FFFFFF',
                      borderRadius: 16,
                      padding: '12px 14px',
                      border: isSelected
                        ? '2px solid #4F46E5'
                        : p.isWinner
                        ? '2px solid #F59E0B'
                        : '2px solid #E2E8F0',
                      boxShadow: isSelected
                        ? '0 3px 0 #312E81'
                        : p.isWinner
                        ? '0 3px 0 #D97706'
                        : '0 2px 0 #CBD5E1',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      transition: 'all 0.1s ease',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: '20px' }}>{medal}</span>
                      <div>
                        <div style={{ fontSize: '14px', fontWeight: 900, color: '#1E1B4B', display: 'flex', alignItems: 'center', gap: 6 }}>
                          {p.name}
                          {isSelected && (
                            <span style={{ fontSize: '9px', backgroundColor: '#EEF2FF', color: '#4F46E5', padding: '1px 5px', borderRadius: 6, fontWeight: 900 }}>
                              Sélectionné
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#64748B' }}>
                          {p.cardsWon} carte(s) • ROI {p.roi} • ${p.spentCash} dépensé
                        </div>
                      </div>
                    </div>

                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '16px', fontWeight: 900, color: '#312E81' }}>
                        {p.score} pts
                      </div>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: '#10B981' }}>
                        {p.cashLeft} dispo
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* BONUS DE SYNERGIES DÉCLENCHÉES */}
        {viewedPlayer && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <h3 style={{ fontSize: '16px', fontWeight: 900, color: '#1E1B4B', margin: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Sparkles size={16} color="#4F46E5" />
                Synergies de {viewedPlayer.name} ({synergies.length})
              </h3>
            </div>

            {synergies.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {synergies.map((s, idx) => (
                  <div
                    key={idx}
                    style={{
                      backgroundColor: '#EEF2FF',
                      borderRadius: 14,
                      padding: '10px 12px',
                      border: '1px solid #C7D2FE',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 800, color: '#312E81' }}>{s.name}</div>
                      <div style={{ fontSize: '11px', color: '#6366F1', fontWeight: 600 }}>{s.description}</div>
                    </div>
                    <span style={{ fontSize: '13px', fontWeight: 900, color: '#4F46E5' }}>+{s.bonus} pts</span>
                  </div>
                ))}
              </div>
            ) : (
              <div
                style={{
                  backgroundColor: '#F8FAFC',
                  borderRadius: 12,
                  padding: '10px 14px',
                  border: '1px dashed #CBD5E1',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#64748B',
                  textAlign: 'center',
                }}
              >
                Aucune synergie d'équipe activée pour ce joueur.
              </div>
            )}
          </div>
        )}

        {/* CARTES RÉELLEMENT REMPORTÉES */}
        {viewedPlayer && (
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 900, color: '#1E1B4B', margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Award size={16} color="#059669" />
              Cartes Remportées par {viewedPlayer.name} ({draftedTeam.length})
            </h3>

            {draftedTeam.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {draftedTeam.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      backgroundColor: '#FFFFFF',
                      borderRadius: 14,
                      padding: '10px 14px',
                      border: '1px solid #E2E8F0',
                      boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 800, color: '#1E1B4B' }}>{item.name}</div>
                      <div style={{ fontSize: '11px', color: '#64748B', fontWeight: 600 }}>
                        Base : {item.score} pts • Achetée ${item.winningBid || 0}
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 800,
                        textTransform: 'uppercase',
                        color:
                          item.rarity?.toLowerCase() === 'legendary'
                            ? '#F59E0B'
                            : item.rarity?.toLowerCase() === 'epic'
                            ? '#8B5CF6'
                            : '#6366F1',
                      }}
                    >
                      ★ {item.rarity}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div
                style={{
                  backgroundColor: '#F8FAFC',
                  borderRadius: 12,
                  padding: '10px 14px',
                  border: '1px dashed #CBD5E1',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#64748B',
                  textAlign: 'center',
                }}
              >
                Aucune carte remportée pendant ce match.
              </div>
            )}
          </div>
        )}

        {/* Boutons d'Action */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 4 }}>
          <Button3D
            variant="neutral"
            size="md"
            fullWidth
            icon={<Home size={18} />}
            onClick={() => onNavigate('home')}
          >
            Accueil
          </Button3D>

          <Button3D
            variant="primary"
            size="md"
            fullWidth
            icon={<RefreshCw size={18} />}
            onClick={onPlayAgain}
          >
            Rejouer
          </Button3D>
        </div>

      </div>
    </div>
  );
};
