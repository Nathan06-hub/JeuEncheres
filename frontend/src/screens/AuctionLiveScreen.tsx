import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  Timer,
  Gavel,
  X,
  Smartphone,
  Check,
  Send,
  Crown,
} from 'lucide-react';
import { ScreenId, DeckItem, Deck, LocalMatchResults } from '../models';
import { TopBar } from '../widgets/TopBar';
import { Button3D } from '../widgets/Button3D';
import { ClueCard } from '../widgets/ClueCard';
import {
  connectAuctionWs,
  fetchAuctionLiveState,
  mockDeckItems,
  submitBidApi,
} from '../services/api';
import { computeLocalGameResults, LocalPlayerState } from '../services/synergyHelper';

export interface AuctionLiveScreenProps {
  tokensCount: number;
  activeDeck?: Deck | null;
  sessionId?: string | null;
  roomCode?: string | null;
  gameMode?: 'LOCAL' | 'ONLINE';
  localPlayers?: string[];
  onNavigate: (screen: ScreenId) => void;
  onFinishMatch: (results?: LocalMatchResults) => void;
}

interface OnlineParticipant {
  id: string;
  name: string;
  cash: number;
  hasPassed: boolean;
  isHost?: boolean;
}

export const AuctionLiveScreen: React.FC<AuctionLiveScreenProps> = ({
  tokensCount,
  activeDeck,
  sessionId,
  roomCode,
  gameMode = 'LOCAL',
  localPlayers = ['Alex', 'Sophie', 'Lucas'],
  onNavigate,
  onFinishMatch,
}) => {
  const isLocalMode = gameMode === 'LOCAL' || (!sessionId && !roomCode);

  // Common Auction State
  const [currentRound, setCurrentRound] = useState(1);
  const [totalRounds, setTotalRounds] = useState(5);
  const [currentBid, setCurrentBid] = useState(0); // starts at 0 for fresh bids
  const [highestBidderName, setHighestBidderName] = useState<string>('Personne');
  const [highestBidderId, setHighestBidderId] = useState<string | null>(null);
  const [roundWinnerAnnounce, setRoundWinnerAnnounce] = useState<string | null>(null);
  const [customBidAmount, setCustomBidAmount] = useState<string>('');
  const [showCustomInput, setShowCustomInput] = useState<boolean>(false);

  // =========================================================================
  // LOCAL PASS & PLAY STATE
  // =========================================================================
  const [localPlayersData, setLocalPlayersData] = useState<LocalPlayerState[]>(() => {
    return localPlayers.map((name, idx) => ({
      id: `local-p-${idx}`,
      name,
      startingBudget: 1000,
      remainingBudget: 1000,
      spentBudget: 0,
      draftedItems: [],
    }));
  });

  // Track who has passed in the CURRENT round
  const [passedPlayerIds, setPassedPlayerIds] = useState<Set<string>>(new Set());

  // Current player turn index in local mode
  const [activePlayerTurnIndex, setActivePlayerTurnIndex] = useState<number>(0);

  // Individual 10-second timer for the active player's turn
  const [turnTimerSeconds, setTurnTimerSeconds] = useState<number>(10);

  // Pass-the-phone transition overlay
  const [isTransitioning, setIsTransitioning] = useState<boolean>(false);
  const [transitionNextPlayer, setTransitionNextPlayer] = useState<LocalPlayerState | null>(null);

  // =========================================================================
  // ONLINE WEBSOCKET STATE
  // =========================================================================
  const [onlineTimerSeconds, setOnlineTimerSeconds] = useState(15);
  const [onlineClueLevel, setOnlineClueLevel] = useState(1);
  const [hasUserPassed, setHasUserPassed] = useState(false);
  const [userBudget, setUserBudget] = useState(1000);
  const [myPlayerId, setMyPlayerId] = useState<string>('p-me');
  const myPlayerIdRef = useRef<string>('p-me');
  const [onlineParticipants, setOnlineParticipants] = useState<OnlineParticipant[]>([]);
  const [onlineItem, setOnlineItem] = useState<DeckItem | null>(null);

  // Refs for reliable timer cleanup
  const winnerTimeoutRef = useRef<any>(null);
  const turnIntervalRef = useRef<any>(null);
  const finishTimeoutRef = useRef<any>(null);

  // Deck items pool
  const itemsPool: DeckItem[] = useMemo(() => {
    if (activeDeck?.items && activeDeck.items.length > 0) {
      return activeDeck.items;
    }
    return mockDeckItems;
  }, [activeDeck]);

  const currentItem: DeckItem = (!isLocalMode && onlineItem)
    ? onlineItem
    : (itemsPool[(currentRound - 1) % itemsPool.length] || mockDeckItems[0]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      const winnerTimer = winnerTimeoutRef.current;
      const turnInterval = turnIntervalRef.current;
      const finishTimer = finishTimeoutRef.current;
      if (winnerTimer) clearTimeout(winnerTimer);
      if (turnInterval) clearInterval(turnInterval);
      if (finishTimer) clearTimeout(finishTimer);
    };
  }, []);

  // Current active player in Local Mode
  const currentActiveLocalPlayer = localPlayersData[activePlayerTurnIndex] || localPlayersData[0];

  // =========================================================================
  // LOCAL PASS & PLAY MECHANICS
  // =========================================================================

  // Find next active player who hasn't passed
  const getNextActivePlayerIndex = useCallback(
    (fromIndex: number, currentPassed: Set<string>): number | null => {
      const total = localPlayersData.length;
      for (let i = 1; i <= total; i++) {
        const nextIdx = (fromIndex + i) % total;
        const candidate = localPlayersData[nextIdx];
        if (!currentPassed.has(candidate.id)) {
          return nextIdx;
        }
      }
      return null;
    },
    [localPlayersData]
  );

  // Resolve local round when only 1 active player remains (or all passed)
  const resolveLocalRound = useCallback(
    (winningPlayerId: string | null, finalBid: number) => {
      if (turnIntervalRef.current) clearInterval(turnIntervalRef.current);

      let winner: LocalPlayerState | null = null;

      if (winningPlayerId && finalBid > 0) {
        // Find winner
        winner = localPlayersData.find((p) => p.id === winningPlayerId) || null;
      }

      if (winner) {
        // Debit winning cash & award card
        setLocalPlayersData((prev) =>
          prev.map((p) => {
            if (p.id === winner!.id) {
              const updatedBudget = Math.max(0, p.remainingBudget - finalBid);
              const wonItem: DeckItem = {
                ...currentItem,
                winningBid: finalBid,
                clueLevelWon: 1, // En local, 1 seul indice affiché d'entrée
              };
              return {
                ...p,
                remainingBudget: updatedBudget,
                spentBudget: p.spentBudget + finalBid,
                draftedItems: [...p.draftedItems, wonItem],
              };
            }
            return p;
          })
        );

        setRoundWinnerAnnounce(
          `🏆 ${winner.name} remporte la carte "${currentItem.name}" pour $${finalBid} !`
        );
      } else {
        setRoundWinnerAnnounce('❌ Aucun joueur n\'a enchéri sur cette carte (Défaussée).');
      }

      // Clear winner toast and advance to next round after 2.8s
      if (winnerTimeoutRef.current) clearTimeout(winnerTimeoutRef.current);
      winnerTimeoutRef.current = setTimeout(() => {
        setRoundWinnerAnnounce(null);

        if (currentRound >= totalRounds) {
          // Game Over: compute results and trigger results screen
          setLocalPlayersData((latestPlayers) => {
            const results = computeLocalGameResults(
              activeDeck?.title || 'Partie Locale',
              totalRounds,
              latestPlayers
            );
            onFinishMatch(results);
            return latestPlayers;
          });
        } else {
          // Start next round
          setCurrentRound((prev) => prev + 1);
          setCurrentBid(0);
          setHighestBidderId(null);
          setHighestBidderName('Personne');
          setPassedPlayerIds(new Set());
          setCustomBidAmount('');
          setShowCustomInput(false);

          // Rotate starting player for the new round
          const newStartIdx = currentRound % localPlayersData.length;
          setActivePlayerTurnIndex(newStartIdx);
          setTurnTimerSeconds(10);

          // Transition to the first player of the new round
          setTransitionNextPlayer(localPlayersData[newStartIdx]);
          setIsTransitioning(true);
        }
      }, 2800);
    },
    [
      localPlayersData,
      currentItem,
      currentRound,
      totalRounds,
      activeDeck,
      onFinishMatch,
    ]
  );

  // Turn advance helper with transition screen
  const advanceToNextTurnOrResolve = useCallback(
    (newBid: number, newBidderId: string | null, newPassedSet: Set<string>) => {
      // Count how many players have NOT passed
      const remainingActivePlayers = localPlayersData.filter((p) => !newPassedSet.has(p.id));

      // Condition de fin de manche :
      // Quand tous les joueurs sauf un ont passé :
      // Si une enchère a été faite (newBidderId !== null), le dernier enchérisseur l'emporte !
      if (remainingActivePlayers.length <= 1) {
        if (remainingActivePlayers.length === 1 && newBidderId) {
          // Le dernier actif ou le plus offrant gagne la carte
          resolveLocalRound(newBidderId, newBid);
          return;
        } else if (remainingActivePlayers.length === 0) {
          // Tout le monde a passé
          resolveLocalRound(newBidderId, newBid);
          return;
        }
      }

      // Manche toujours en cours : trouver le joueur actif suivant
      const nextIdx = getNextActivePlayerIndex(activePlayerTurnIndex, newPassedSet);
      if (nextIdx !== null) {
        const nextPlayer = localPlayersData[nextIdx];
        setTransitionNextPlayer(nextPlayer);
        setIsTransitioning(true); // Affiche "Passe le téléphone à [Joueur Suivant]"
        setActivePlayerTurnIndex(nextIdx);
        setTurnTimerSeconds(10);
        setCustomBidAmount('');
        setShowCustomInput(false);
      } else {
        // Plus aucun joueur suivant disponible
        resolveLocalRound(newBidderId, newBid);
      }
    },
    [
      localPlayersData,
      activePlayerTurnIndex,
      getNextActivePlayerIndex,
      resolveLocalRound,
    ]
  );

  // Player passes their turn
  const handleLocalPass = useCallback(() => {
    const newPassed = new Set(passedPlayerIds);
    newPassed.add(currentActiveLocalPlayer.id);
    setPassedPlayerIds(newPassed);

    advanceToNextTurnOrResolve(currentBid, highestBidderId, newPassed);
  }, [
    passedPlayerIds,
    currentActiveLocalPlayer.id,
    advanceToNextTurnOrResolve,
    currentBid,
    highestBidderId,
  ]);

  // Turn timer countdown (10 seconds)
  useEffect(() => {
    if (!isLocalMode || isTransitioning || roundWinnerAnnounce) {
      if (turnIntervalRef.current) clearInterval(turnIntervalRef.current);
      return;
    }

    if (turnIntervalRef.current) clearInterval(turnIntervalRef.current);
    turnIntervalRef.current = setInterval(() => {
      setTurnTimerSeconds((prev) => {
        if (prev <= 1) {
          // Expired: player passes automatically!
          clearInterval(turnIntervalRef.current);
          handleLocalPass();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (turnIntervalRef.current) clearInterval(turnIntervalRef.current);
    };
  }, [
    isLocalMode,
    activePlayerTurnIndex,
    isTransitioning,
    roundWinnerAnnounce,
    handleLocalPass,
  ]);

  // Handle local bid (+1, +5, +25, or custom)
  const handleLocalPlaceBid = (amountToAddOrTotal: number, isAbsolute: boolean = false) => {
    const targetBid = isAbsolute ? amountToAddOrTotal : currentBid + amountToAddOrTotal;

    // Must be strictly superior to current bid
    if (targetBid <= currentBid) {
      alert(`Votre enchère doit être supérieure à l'offre actuelle ($${currentBid}).`);
      return;
    }

    // Must not exceed player budget
    if (targetBid > currentActiveLocalPlayer.remainingBudget) {
      alert(
        `Budget insuffisant pour ${currentActiveLocalPlayer.name} (Solde : $${currentActiveLocalPlayer.remainingBudget}).`
      );
      return;
    }

    setCurrentBid(targetBid);
    setHighestBidderId(currentActiveLocalPlayer.id);
    setHighestBidderName(currentActiveLocalPlayer.name);

    // Passer le téléphone au joueur actif suivant
    advanceToNextTurnOrResolve(targetBid, currentActiveLocalPlayer.id, passedPlayerIds);
  };

  // Submit custom bid input
  const handleValidateCustomBid = () => {
    const parsed = parseInt(customBidAmount, 10);
    if (isNaN(parsed) || parsed <= currentBid) {
      alert(`Veuillez entrer un montant supérieur à l'enchère actuelle ($${currentBid}).`);
      return;
    }
    if (isLocalMode) {
      handleLocalPlaceBid(parsed, true);
    } else {
      handleOnlinePlaceBid(parsed, true);
    }
  };

  // User confirms ready on pass-the-phone transition screen
  const handleConfirmReadyNextPlayer = () => {
    setIsTransitioning(false);
    setTurnTimerSeconds(10);
  };

  // =========================================================================
  // ONLINE WEBSOCKET INTEGRATION
  // =========================================================================
  const syncOnlineLiveState = useCallback((sid: string) => {
    fetchAuctionLiveState(sid)
      .then((state) => {
        if (!state) return;
        setCurrentRound(state.current_round || 1);
        setTotalRounds(state.total_rounds || 5);
        setOnlineClueLevel(state.current_clue_level || 1);
        if (state.timer_seconds) setOnlineTimerSeconds(state.timer_seconds);
        if (state.item) {
          setOnlineItem({
            id: state.item.id,
            name: state.item.name || '???',
            clue1: state.item.clue_1 || '',
            clue2: state.item.clue_2 || '',
            clue3: state.item.clue_3 || '',
            score: state.item.base_score || 0,
            rarity: 'rare',
            category: state.item.category || 'POP_CULTURE',
          });
        }
        if (state.players && state.players.length > 0) {
          setOnlineParticipants(
            state.players.map((p: any) => ({
              id: p.id,
              name: p.display_name,
              cash: p.remaining_budget,
              hasPassed: false,
              isHost: p.is_host,
            }))
          );
          const me = state.players.find((p: any) => p.id === myPlayerIdRef.current);
          if (me && typeof me.remaining_budget === 'number') {
            setUserBudget(me.remaining_budget);
          }
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (isLocalMode || !sessionId) return;

    // Fetch initial state via REST
    syncOnlineLiveState(sessionId);

    // Open real-time WebSocket connection
    const cleanupWs = connectAuctionWs(sessionId, {
      onMessage: (msg) => {
        if (msg.type === 'CONNECTED') {
          if (msg.player_id) {
            myPlayerIdRef.current = msg.player_id;
            setMyPlayerId(msg.player_id);
          }
        } else if (msg.type === 'STATE_SNAPSHOT') {
          if (msg.round) setCurrentRound(msg.round);
          if (msg.total_rounds) setTotalRounds(msg.total_rounds);
          if (msg.clue_level) setOnlineClueLevel(msg.clue_level);
          syncOnlineLiveState(sessionId);
        } else if (msg.type === 'PLAYER_JOINED') {
          setOnlineParticipants((prev) => {
            if (prev.some((p) => p.id === msg.player_id)) return prev;
            return [
              ...prev,
              {
                id: msg.player_id,
                name: msg.display_name,
                cash: msg.remaining_budget || 1000,
                hasPassed: false,
              },
            ];
          });
        } else if (msg.type === 'TIMER_TICK') {
          setOnlineTimerSeconds(msg.seconds_left);
          if (msg.round) setCurrentRound(msg.round);
          if (msg.clue_level) setOnlineClueLevel(msg.clue_level);
        } else if (msg.type === 'CLUE_REVEALED') {
          setOnlineClueLevel(msg.clue_level);
          syncOnlineLiveState(sessionId);
        } else if (msg.type === 'NEW_BID') {
          setCurrentBid(msg.amount);
          setHighestBidderId(msg.player_id);
          setOnlineParticipants((prev) => {
            const bidder = prev.find((p) => p.id === msg.player_id);
            if (bidder) setHighestBidderName(bidder.name);
            return prev;
          });
        } else if (msg.type === 'PLAYER_PASSED') {
          setOnlineParticipants((prev) =>
            prev.map((p) => (p.id === msg.player_id ? { ...p, hasPassed: true } : p))
          );
        } else if (msg.type === 'ROUND_RESOLVED') {
          setRoundWinnerAnnounce(
            msg.winner_name
              ? `🏆 ${msg.winner_name} remporte la carte "${msg.item_name || ''}" pour $${msg.winning_amount} !`
              : 'Aucun gagnant pour cette manche'
          );
          if (winnerTimeoutRef.current) clearTimeout(winnerTimeoutRef.current);
          winnerTimeoutRef.current = setTimeout(() => {
            setRoundWinnerAnnounce(null);
          }, 3000);

          if (msg.winner_player_id === myPlayerIdRef.current && typeof msg.winning_amount === 'number') {
            setUserBudget((prev) => Math.max(0, prev - msg.winning_amount));
          }

          setOnlineParticipants((prev) =>
            prev.map((p) => {
              if (p.id === msg.winner_player_id && typeof msg.winning_amount === 'number') {
                return { ...p, cash: Math.max(0, p.cash - msg.winning_amount), hasPassed: false };
              }
              return { ...p, hasPassed: false };
            })
          );

          setHasUserPassed(false);
          setCurrentBid(0);
          setHighestBidderName('Personne');
          setHighestBidderId(null);
          syncOnlineLiveState(sessionId);
        } else if (msg.type === 'GAME_FINISHED') {
          onFinishMatch();
        }
      },
      onError: (err) => {
        console.warn('WS live error:', err);
      },
    });

    return () => {
      cleanupWs();
    };
  }, [isLocalMode, sessionId, onFinishMatch, syncOnlineLiveState]);

  // Online Place Bid
  const handleOnlinePlaceBid = async (amountToAddOrTotal: number, isAbsolute: boolean = false) => {
    const targetBid = isAbsolute ? amountToAddOrTotal : currentBid + amountToAddOrTotal;

    if (userBudget < targetBid) {
      alert(`Budget insuffisant ($${userBudget} disponible).`);
      return;
    }

    try {
      if (sessionId) {
        await submitBidApi(sessionId, myPlayerId, targetBid, false);
      }
      setCurrentBid(targetBid);
      setHighestBidderId(myPlayerId);
      setHighestBidderName('Moi');
      setCustomBidAmount('');
      setShowCustomInput(false);
    } catch (err: any) {
      alert(err.message || "Erreur lors de l'enchère");
    }
  };

  const handleOnlinePass = async () => {
    setHasUserPassed(true);
    if (sessionId) {
      try {
        await submitBidApi(sessionId, myPlayerId, 0, true);
      } catch {
        // ignore
      }
    }
  };

  // Revealed clues count: exactly 1 in local Pass & Play, or online level
  const displayedClueLevel = isLocalMode ? 1 : onlineClueLevel;

  return (
    <div style={{ paddingBottom: 28, display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Top Header */}
      <TopBar
        title={`Manche ${currentRound} / ${totalRounds}`}
        tokensCount={tokensCount}
        onTokensClick={() => onNavigate('shop')}
      />

      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        
        {/* Mode Indicator Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#FFFFFF',
            padding: '10px 14px',
            borderRadius: 18,
            border: '2px solid #E2E8F0',
            boxShadow: '0 2px 0 #CBD5E1',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                backgroundColor: isLocalMode ? '#F59E0B' : '#10B981',
                boxShadow: `0 0 0 3px ${isLocalMode ? '#FEF3C7' : '#D1FAE5'}`,
              }}
            />
            <span style={{ fontSize: '13px', fontWeight: 900, color: '#1E1B4B' }}>
              {isLocalMode ? '📱 MODE PASS & PLAY' : '🌐 EN DIRECT WEBSOCKET'}
            </span>
          </div>

          {/* Session code pill if online */}
          {!isLocalMode && roomCode && (
            <span
              style={{
                fontSize: '11px',
                fontWeight: 900,
                backgroundColor: '#EEF2FF',
                color: '#4F46E5',
                padding: '3px 8px',
                borderRadius: 8,
                fontFamily: 'monospace',
              }}
            >
              CODE : {roomCode}
            </span>
          )}

          {/* General Timer indicator for online mode */}
          {!isLocalMode && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                backgroundColor: onlineTimerSeconds <= 5 ? '#FFE4E6' : '#EEF2FF',
                color: onlineTimerSeconds <= 5 ? '#E11D48' : '#312E81',
                border: `2px solid ${onlineTimerSeconds <= 5 ? '#FDA4AF' : '#C7D2FE'}`,
                padding: '3px 10px',
                borderRadius: 12,
                fontWeight: 900,
                fontSize: '13px',
              }}
            >
              <Timer size={15} />
              00:{onlineTimerSeconds < 10 ? `0${onlineTimerSeconds}` : onlineTimerSeconds}
            </div>
          )}
        </div>

        {/* ========================================================================= */}
        {/* BANDEAU TRÈS LISIBLE EN MODE LOCAL : "C'EST À [NOM] DE JOUER" */}
        {/* ========================================================================= */}
        {isLocalMode && (
          <div
            style={{
              backgroundColor: '#064E3B',
              borderRadius: 20,
              padding: '14px 16px',
              border: '3px solid #047857',
              boxShadow: '0 4px 0 #022C22',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              color: '#FFFFFF',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 12,
                  backgroundColor: '#10B981',
                  color: '#FFFFFF',
                  fontWeight: 900,
                  fontSize: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 2px 0 #059669',
                }}
              >
                {currentActiveLocalPlayer.name.charAt(0).toUpperCase()}
              </div>
              <div>
                <div style={{ fontSize: '11px', fontWeight: 800, color: '#A7F3D0', textTransform: 'uppercase' }}>
                  Tour actif
                </div>
                <div style={{ fontSize: '17px', fontWeight: 900, color: '#FFFFFF' }}>
                  C'est à <span style={{ color: '#FCD34D' }}>{currentActiveLocalPlayer.name}</span> de jouer
                </div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#A7F3D0' }}>
                  Solde dédié : <strong style={{ color: '#FFFFFF' }}>${currentActiveLocalPlayer.remainingBudget}</strong>
                </div>
              </div>
            </div>

            {/* Individual 10-second countdown timer */}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                backgroundColor: turnTimerSeconds <= 3 ? '#E11D48' : '#047857',
                padding: '6px 12px',
                borderRadius: 14,
                border: '2px solid rgba(255,255,255,0.2)',
                minWidth: 50,
              }}
            >
              <span style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', color: '#D1FAE5' }}>
                Chrono
              </span>
              <span style={{ fontSize: '18px', fontWeight: 900, color: '#FFFFFF' }}>
                {turnTimerSeconds}s
              </span>
            </div>
          </div>
        )}

        {/* Central Progressive Clue Card (1 seul indice d'entrée en local) */}
        <ClueCard item={currentItem} revealedCount={displayedClueLevel} />

        {/* Winner Toast Notification */}
        {roundWinnerAnnounce && (
          <div
            style={{
              backgroundColor: '#FEF3C7',
              border: '2px solid #F59E0B',
              borderRadius: 16,
              padding: '12px 16px',
              color: '#92400E',
              fontWeight: 800,
              fontSize: '14px',
              textAlign: 'center',
              boxShadow: '0 3px 0 #D97706',
              animation: 'pulse 1s infinite',
            }}
          >
            {roundWinnerAnnounce}
          </div>
        )}

        {/* Current High Bid Display */}
        <div
          style={{
            backgroundColor: '#312E81',
            borderRadius: 20,
            border: '3px solid #1E1B4B',
            boxShadow: '0 4px 0 #1E1B4B',
            padding: '14px 18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            color: '#FFFFFF',
          }}
        >
          <div>
            <div style={{ fontSize: '11px', fontWeight: 800, color: '#C7D2FE', textTransform: 'uppercase' }}>
              Offre la plus haute
            </div>
            <div style={{ fontSize: '26px', fontWeight: 900, color: '#FCD34D' }}>
              ${currentBid}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '11px', fontWeight: 800, color: '#C7D2FE', textTransform: 'uppercase' }}>
              Meneur actuel
            </div>
            <div style={{ fontSize: '15px', fontWeight: 900, color: '#FFFFFF', display: 'flex', alignItems: 'center', gap: 5, justifyContent: 'flex-end' }}>
              <Crown size={16} color="#F59E0B" />
              {highestBidderName}
            </div>
          </div>
        </div>

        {/* Participants Table */}
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: 18,
            border: '2px solid #E2E8F0',
            boxShadow: '0 2px 0 #CBD5E1',
            padding: '12px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          <span style={{ fontSize: '11px', fontWeight: 800, color: '#64748B', textTransform: 'uppercase' }}>
            Joueurs de la Table ({isLocalMode ? localPlayersData.length : onlineParticipants.length})
          </span>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {isLocalMode
              ? localPlayersData.map((p, idx) => {
                  const isCurrentTurn = idx === activePlayerTurnIndex;
                  const isLeading = highestBidderId === p.id;
                  const hasPassed = passedPlayerIds.has(p.id);

                  let statusText = 'En attente';
                  if (hasPassed) statusText = 'Passé';
                  else if (isLeading) statusText = '👑 Meneur';
                  else if (isCurrentTurn) statusText = '👉 Son tour';

                  return (
                    <div
                      key={p.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 10px',
                        borderRadius: 12,
                        backgroundColor: isCurrentTurn ? '#ECFDF5' : '#F8FAFC',
                        border: isCurrentTurn ? '2px solid #10B981' : '1px solid #E2E8F0',
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '12px', fontWeight: 800, color: '#1E1B4B' }}>{p.name}</div>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#10B981' }}>
                          ${p.remainingBudget}
                        </div>
                      </div>
                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 800,
                          padding: '2px 6px',
                          borderRadius: 8,
                          backgroundColor: isLeading
                            ? '#FEF3C7'
                            : hasPassed
                            ? '#F1F5F9'
                            : isCurrentTurn
                            ? '#DCFCE7'
                            : '#EEF2FF',
                          color: isLeading
                            ? '#B45309'
                            : hasPassed
                            ? '#94A3B8'
                            : isCurrentTurn
                            ? '#065F46'
                            : '#4F46E5',
                        }}
                      >
                        {statusText}
                      </span>
                    </div>
                  );
                })
              : onlineParticipants.map((p) => {
                  const isLeading = highestBidderId === p.id;
                  const statusText = isLeading ? '👑 En tête' : p.hasPassed ? 'Passé' : 'Actif';
                  const displayCash = p.id === myPlayerId ? `$${userBudget}` : `$${p.cash}`;
                  return (
                    <div
                      key={p.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '8px 10px',
                        borderRadius: 12,
                        backgroundColor: '#F8FAFC',
                        border: '1px solid #E2E8F0',
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '12px', fontWeight: 800, color: '#1E1B4B' }}>
                          {p.name} {p.id === myPlayerId ? '(Moi)' : ''}
                        </div>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#10B981' }}>{displayCash}</div>
                      </div>
                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 800,
                          padding: '2px 6px',
                          borderRadius: 8,
                          backgroundColor: isLeading ? '#FEF3C7' : p.hasPassed ? '#F1F5F9' : '#EEF2FF',
                          color: isLeading ? '#B45309' : p.hasPassed ? '#94A3B8' : '#4F46E5',
                        }}
                      >
                        {statusText}
                      </span>
                    </div>
                  );
                })}
          </div>
        </div>

        {/* ========================================================================= */}
        {/* ACTIONS D'ENCHÈRES : LIBERTÉ TOTALE (+1$, +5$, +25$ ET SAISIE LIBRE) */}
        {/* ========================================================================= */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 4 }}>
          {/* Surenchères Rapides Fine (+1 $, +5 $, +25 $) */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            <Button3D
              variant="neutral"
              size="sm"
              disabled={isLocalMode ? passedPlayerIds.has(currentActiveLocalPlayer.id) : hasUserPassed}
              onClick={() => (isLocalMode ? handleLocalPlaceBid(1) : handleOnlinePlaceBid(1))}
            >
              +$1
            </Button3D>
            <Button3D
              variant="neutral"
              size="sm"
              disabled={isLocalMode ? passedPlayerIds.has(currentActiveLocalPlayer.id) : hasUserPassed}
              onClick={() => (isLocalMode ? handleLocalPlaceBid(5) : handleOnlinePlaceBid(5))}
            >
              +$5
            </Button3D>
            <Button3D
              variant="neutral"
              size="sm"
              disabled={isLocalMode ? passedPlayerIds.has(currentActiveLocalPlayer.id) : hasUserPassed}
              onClick={() => (isLocalMode ? handleLocalPlaceBid(25) : handleOnlinePlaceBid(25))}
            >
              +$25
            </Button3D>
          </div>

          {/* Saisie Libre / Pavé Numérique Toggle */}
          {showCustomInput ? (
            <div
              style={{
                display: 'flex',
                gap: 8,
                backgroundColor: '#FFFFFF',
                padding: '8px',
                borderRadius: 14,
                border: '2px solid #CBD5E1',
              }}
            >
              <input
                type="number"
                min={currentBid + 1}
                value={customBidAmount}
                onChange={(e) => setCustomBidAmount(e.target.value)}
                placeholder={`Montant > $${currentBid}`}
                style={{
                  flex: 1,
                  padding: '8px 12px',
                  borderRadius: 10,
                  border: '1px solid #94A3B8',
                  fontSize: '15px',
                  fontWeight: 800,
                  outline: 'none',
                  color: '#1E1B4B',
                }}
              />
              <Button3D
                variant="primary"
                size="sm"
                onClick={handleValidateCustomBid}
                icon={<Send size={14} />}
              >
                Valider
              </Button3D>
              <button
                onClick={() => setShowCustomInput(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: '4px 8px',
                  color: '#64748B',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                Annuler
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowCustomInput(true)}
              style={{
                padding: '8px',
                borderRadius: 12,
                border: '2px dashed #94A3B8',
                backgroundColor: '#F8FAFC',
                color: '#475569',
                fontSize: '12px',
                fontWeight: 800,
                cursor: 'pointer',
                textAlign: 'center',
              }}
            >
              ✏️ Saisir un montant personnalisé
            </button>
          )}

          {/* Action principale : Passer ou Enchérir */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 10 }}>
            <Button3D
              variant="neutral"
              size="md"
              disabled={isLocalMode ? passedPlayerIds.has(currentActiveLocalPlayer.id) : hasUserPassed}
              onClick={isLocalMode ? handleLocalPass : handleOnlinePass}
              icon={<X size={16} />}
            >
              Passer
            </Button3D>

            <Button3D
              variant="success"
              size="md"
              disabled={isLocalMode ? passedPlayerIds.has(currentActiveLocalPlayer.id) : hasUserPassed}
              onClick={() => (isLocalMode ? handleLocalPlaceBid(1) : handleOnlinePlaceBid(1))}
              icon={<Gavel size={18} />}
            >
              Enchérir (${currentBid + 1})
            </Button3D>
          </div>
        </div>

      </div>

      {/* ========================================================================= */}
      {/* ÉCRAN DE TRANSITION RAPIDE : "PASSE LE TÉLÉPHONE À [JOUEUR SUIVANT]" */}
      {/* ========================================================================= */}
      {isLocalMode && isTransitioning && transitionNextPlayer && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.88)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 150,
            padding: 20,
          }}
        >
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: 28,
              border: '4px solid #10B981',
              boxShadow: '0 20px 40px rgba(0,0,0,0.4)',
              width: '100%',
              maxWidth: 360,
              padding: '28px 20px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              textAlign: 'center',
              gap: 16,
            }}
          >
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: '50%',
                backgroundColor: '#ECFDF5',
                border: '3px solid #10B981',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#059669',
              }}
            >
              <Smartphone size={36} />
            </div>

            <div>
              <span
                style={{
                  backgroundColor: '#FEF3C7',
                  color: '#B45309',
                  fontSize: '11px',
                  fontWeight: 900,
                  padding: '4px 10px',
                  borderRadius: 10,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                }}
              >
                Changement de joueur
              </span>

              <h2 style={{ fontSize: '20px', fontWeight: 900, color: '#1E1B4B', margin: '10px 0 4px' }}>
                Passe le téléphone à :
              </h2>

              <div
                style={{
                  fontSize: '26px',
                  fontWeight: 900,
                  color: '#059669',
                  padding: '4px 0',
                }}
              >
                {transitionNextPlayer.name}
              </div>

              <div style={{ fontSize: '13px', fontWeight: 700, color: '#64748B', marginTop: 4 }}>
                Solde disponible : <strong style={{ color: '#10B981' }}>${transitionNextPlayer.remainingBudget}</strong>
              </div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#F59E0B', marginTop: 2 }}>
                Offre actuelle à battre : <strong>${currentBid}</strong>
              </div>
            </div>

            <Button3D
              variant="success"
              size="lg"
              fullWidth
              icon={<Check size={20} />}
              onClick={handleConfirmReadyNextPlayer}
            >
              C'EST À MOI ! (10s)
            </Button3D>
          </div>
        </div>
      )}

    </div>
  );
};
