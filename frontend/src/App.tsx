import React, { useState, useEffect, useCallback } from 'react';
import { ScreenId, Deck, LocalMatchResults } from './models';
import { HomeScreen } from './screens/HomeScreen';
import { CreationAiScreen } from './screens/CreationAiScreen';
import { AuctionLiveScreen } from './screens/AuctionLiveScreen';
import { ResultsScreen } from './screens/ResultsScreen';
import { ShopScreen } from './screens/ShopScreen';
import { BottomNavBar } from './widgets/BottomNavBar';
import { Smartphone, Monitor } from 'lucide-react';
import { ensureGuestAuth, fetchHomeSummary } from './services/api';

export const App: React.FC = () => {
  const [activeScreen, setActiveScreen] = useState<ScreenId>('home');
  const [tokensCount, setTokensCount] = useState<number>(3);
  const [playerName, setPlayerName] = useState<string>('Alex');
  const [isPhoneFrame, setIsPhoneFrame] = useState<boolean>(true);
  const [activeDeck, setActiveDeck] = useState<Deck | null>(null);

  // Game Mode & Match Management
  const [gameMode, setGameMode] = useState<'LOCAL' | 'ONLINE'>('LOCAL');
  const [localPlayers, setLocalPlayers] = useState<string[]>(['Alex', 'Sophie', 'Lucas']);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeRoomCode, setActiveRoomCode] = useState<string | null>(null);
  const [lastMatchResults, setLastMatchResults] = useState<LocalMatchResults | null>(null);

  // Initialize guest authentication & load live profile summary
  const refreshUserData = useCallback(async () => {
    try {
      await ensureGuestAuth();
      const summary = await fetchHomeSummary();
      setTokensCount(summary.userBalance);
      if (summary.username && summary.username !== 'Invité') {
        setPlayerName(summary.username);
      }
    } catch (e) {
      console.warn('Erreur synchronisation profil:', e);
    }
  }, []);

  useEffect(() => {
    refreshUserData();
  }, [refreshUserData]);

  // Démarrer en Mode Soirée Locale (Pass & Play)
  const handleStartLocalGame = (deck: Deck, players: string[]) => {
    setActiveDeck(deck);
    setGameMode('LOCAL');
    setLocalPlayers(players);
    setActiveSessionId(null);
    setActiveRoomCode(null);
    setLastMatchResults(null);
    setActiveScreen('auction');
  };

  // Démarrer en Mode Multijoueur en Ligne
  const handleStartOnlineGame = (deck: Deck, sessionId?: string, roomCode?: string) => {
    setActiveDeck(deck);
    setGameMode('ONLINE');
    setActiveSessionId(sessionId || null);
    setActiveRoomCode(roomCode || null);
    setLastMatchResults(null);
    setActiveScreen('auction');
  };

  const handleConsumeToken = (): boolean => {
    if (tokensCount >= 1) {
      setTokensCount((prev) => prev - 1);
      return true;
    }
    return false;
  };

  const handleAddTokens = (amount: number) => {
    setTokensCount((prev) => prev + amount);
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#E2E8F0',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: isPhoneFrame ? '20px 10px' : '0',
        fontFamily: "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      {/* Top Device Bar */}
      <div
        style={{
          width: '100%',
          maxWidth: 430,
          marginBottom: 10,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 8px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '13px', fontWeight: 800, color: '#312E81' }}>
          <span>🎮 Enchères & Drafts IA</span>
          <span style={{ fontSize: '11px', backgroundColor: '#FEF3C7', color: '#B45309', padding: '2px 6px', borderRadius: 6 }}>
            v0.2.0 Multi & Local
          </span>
        </div>

        <button
          onClick={() => setIsPhoneFrame(!isPhoneFrame)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            fontSize: '12px',
            fontWeight: 700,
            padding: '4px 10px',
            borderRadius: 10,
            border: '1px solid #CBD5E1',
            backgroundColor: '#FFFFFF',
            color: '#1E1B4B',
            cursor: 'pointer',
          }}
        >
          {isPhoneFrame ? <Monitor size={14} /> : <Smartphone size={14} />}
          {isPhoneFrame ? 'Plein Écran' : 'Cadre Mobile'}
        </button>
      </div>

      {/* Mobile Screen Container */}
      <div
        style={{
          width: '100%',
          maxWidth: isPhoneFrame ? 420 : '100%',
          minHeight: isPhoneFrame ? '844px' : '100vh',
          height: isPhoneFrame ? '844px' : '100vh',
          backgroundColor: '#F7F9FD',
          borderRadius: isPhoneFrame ? 36 : 0,
          boxShadow: isPhoneFrame ? '0 16px 36px -4px rgba(15, 23, 42, 0.25), 0 0 0 10px #1E293B' : 'none',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* iOS / Mobile Status Bar simulation */}
        {isPhoneFrame && (
          <div
            style={{
              height: 28,
              backgroundColor: '#FFFFFF',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 20px',
              fontSize: '11px',
              fontWeight: 800,
              color: '#1E1B4B',
              borderBottom: '1px solid #F1F5F9',
              zIndex: 60,
              userSelect: 'none',
            }}
          >
            <span>09:41</span>
            <div style={{ width: 120, height: 16, backgroundColor: '#0F172A', borderRadius: 10, margin: '0 auto' }} />
            <span>100% ⚡</span>
          </div>
        )}

        {/* Scrollable Screen Content */}
        <main
          style={{
            flex: 1,
            overflowY: 'auto',
            WebkitOverflowScrolling: 'touch',
          }}
        >
          {activeScreen === 'home' && (
            <HomeScreen
              tokensCount={tokensCount}
              playerName={playerName}
              onNavigate={setActiveScreen}
              onStartLocalGame={handleStartLocalGame}
              onStartOnlineGame={handleStartOnlineGame}
            />
          )}

          {activeScreen === 'creation' && (
            <CreationAiScreen
              tokensCount={tokensCount}
              onNavigate={setActiveScreen}
              onDeckCreated={(newDeck) => {
                setActiveDeck(newDeck);
                refreshUserData();
              }}
              onConsumeToken={handleConsumeToken}
            />
          )}

          {activeScreen === 'auction' && (
            <AuctionLiveScreen
              tokensCount={tokensCount}
              activeDeck={activeDeck}
              gameMode={gameMode}
              localPlayers={localPlayers}
              sessionId={activeSessionId}
              roomCode={activeRoomCode}
              onNavigate={setActiveScreen}
              onFinishMatch={(results) => {
                if (results) setLastMatchResults(results);
                setActiveScreen('results');
              }}
            />
          )}

          {activeScreen === 'results' && (
            <ResultsScreen
              tokensCount={tokensCount}
              sessionId={activeSessionId}
              localResults={lastMatchResults}
              onNavigate={setActiveScreen}
              onPlayAgain={() => {
                if (gameMode === 'LOCAL' && activeDeck) {
                  handleStartLocalGame(activeDeck, localPlayers);
                } else if (activeDeck) {
                  handleStartOnlineGame(activeDeck, activeSessionId || undefined, activeRoomCode || undefined);
                } else {
                  setActiveScreen('home');
                }
              }}
            />
          )}

          {activeScreen === 'shop' && (
            <ShopScreen
              tokensCount={tokensCount}
              onNavigate={setActiveScreen}
              onAddTokens={(amount) => {
                handleAddTokens(amount);
                refreshUserData();
              }}
            />
          )}
        </main>

        {/* Persistent Bottom Nav Bar */}
        <BottomNavBar
          activeScreen={activeScreen}
          onNavigate={setActiveScreen}
        />
      </div>
    </div>
  );
};

export default App;
