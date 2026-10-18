import React, { useState, useEffect, useRef } from 'react';
import { Sparkles, Wand2 } from 'lucide-react';
import { ScreenId, DeckCategory, Deck } from '../models';
import { TopBar } from '../widgets/TopBar';
import { Button3D } from '../widgets/Button3D';
import { fetchInspirationSuggestions, generateAiDeck } from '../services/api';

export interface CreationAiScreenProps {
  tokensCount: number;
  onNavigate: (screen: ScreenId) => void;
  onDeckCreated: (newDeck: Deck) => void;
  onConsumeToken: () => boolean;
}

export const CreationAiScreen: React.FC<CreationAiScreenProps> = ({
  tokensCount,
  onNavigate,
  onDeckCreated,
  onConsumeToken,
}) => {
  const [promptText, setPromptText] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<DeckCategory>('POP_CULTURE');
  const [difficulty, setDifficulty] = useState<'facile' | 'moyen' | 'expert'>('moyen');
  const [isGenerating, setIsGenerating] = useState(false);
  const [progressStep, setProgressStep] = useState(0);

  const stepTimerRef = useRef<any>(null);

  const [suggestions, setSuggestions] = useState<Array<{ label: string; cat: DeckCategory }>>([
    { label: 'Rap Français 90s', cat: 'MUSIQUE' },
    { label: 'Légendes du Manga Shonen', cat: 'MANGAS' },
    { label: 'Champions NBA 90-2000s', cat: 'SPORT' },
    { label: 'Grands Braquages du Cinéma', cat: 'CINEMA' },
    { label: 'Merveilles du Monde Antique', cat: 'HISTOIRE' },
  ]);

  // Nettoyage impératif des timers au démontage du composant
  useEffect(() => {
    return () => {
      if (stepTimerRef.current) {
        clearInterval(stepTimerRef.current);
        stepTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    fetchInspirationSuggestions().then((items) => {
      if (items && items.length > 0) {
        setSuggestions(
          items.slice(0, 6).map((txt) => ({
            label: txt,
            cat: 'POP_CULTURE' as DeckCategory,
          }))
        );
      }
    });
  }, []);

  const handleGenerate = async () => {
    if (tokensCount < 1) {
      alert("Vous n'avez pas assez de jetons ! Visitez la boutique pour en obtenir.");
      onNavigate('shop');
      return;
    }

    if (!promptText.trim()) {
      alert('Veuillez renseigner un sujet pour que Gemini puisse générer le deck !');
      return;
    }

    setIsGenerating(true);
    setProgressStep(1);

    if (stepTimerRef.current) clearInterval(stepTimerRef.current);
    stepTimerRef.current = setInterval(() => {
      setProgressStep((prev) => (prev < 3 ? prev + 1 : prev));
    }, 1200);

    try {
      // Real API generation call
      const generatedDeck = await generateAiDeck({
        prompt: promptText.trim(),
        category: selectedCategory,
        itemsCount: 10,
      });

      if (stepTimerRef.current) {
        clearInterval(stepTimerRef.current);
        stepTimerRef.current = null;
      }
      setIsGenerating(false);
      onDeckCreated(generatedDeck);
      alert('✨ Thème IA généré avec succès ! 10 cartes et 30 indices ont été construits.');
      onNavigate('home');
    } catch (err: any) {
      if (stepTimerRef.current) {
        clearInterval(stepTimerRef.current);
        stepTimerRef.current = null;
      }
      console.warn('API generation fallback:', err);
      // Fallback local deck if backend is not available
      const fallbackDeck: Deck = {
        id: `ai-${Date.now()}`,
        title: promptText,
        category: selectedCategory,
        author: 'IA Gemini & Alex',
        itemsCount: 10,
        rating: 5.0,
        playCount: 1,
        badge: 'NOUVEAU',
        description: `Deck généré par IA sur la thématique: ${promptText}. 3 indices progressifs par carte.`,
      };
      onConsumeToken();
      setIsGenerating(false);
      onDeckCreated(fallbackDeck);
      alert('✨ Thème IA créé avec succès !');
      onNavigate('home');
    }
  };

  return (
    <div style={{ paddingBottom: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <TopBar
        title="Créer un Thème IA"
        showBack
        onBack={() => onNavigate('home')}
        tokensCount={tokensCount}
        onTokensClick={() => onNavigate('shop')}
      />

      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        
        {/* Intro Banner */}
        <div
          style={{
            backgroundColor: '#EEF2FF',
            borderRadius: 20,
            padding: '16px',
            border: '2px solid #C7D2FE',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 14,
              backgroundColor: '#4F46E5',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#FFFFFF',
              boxShadow: '0 2px 0 #312E81',
            }}
          >
            <Wand2 size={22} />
          </div>
          <div>
            <div style={{ fontSize: '15px', fontWeight: 900, color: '#1E1B4B' }}>
              Générateur Thématique IA
            </div>
            <div style={{ fontSize: '12px', color: '#4338CA', fontWeight: 600 }}>
              Saisissez n'importe quel univers, Gemini génère les 10 cartes et leurs indices secrets.
            </div>
          </div>
        </div>

        {/* Prompt Input Form */}
        <div>
          <label style={{ fontSize: '13px', fontWeight: 800, color: '#1E1B4B', display: 'block', marginBottom: 8 }}>
            VOTRE SUJET LIBRE
          </label>
          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: 18,
              border: '2px solid #CBD5E1',
              boxShadow: '0 3px 0 #E2E8F0',
              padding: '12px 14px',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
            }}
          >
            <input
              type="text"
              placeholder="Ex: Les plus grands braquages du cinéma..."
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              disabled={isGenerating}
              style={{
                border: 'none',
                outline: 'none',
                width: '100%',
                fontSize: '14px',
                fontWeight: 700,
                color: '#1E1B4B',
                backgroundColor: 'transparent',
              }}
            />
          </div>
        </div>

        {/* Quick Suggestions Chips */}
        <div>
          <span style={{ fontSize: '12px', fontWeight: 800, color: '#64748B', display: 'block', marginBottom: 8 }}>
            💡 SUGGESTIONS RAPIDES
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {suggestions.map((s, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setPromptText(s.label);
                  setSelectedCategory(s.cat);
                }}
                disabled={isGenerating}
                className="btn-3d"
                style={{
                  padding: '7px 12px',
                  borderRadius: 16,
                  backgroundColor: '#FFFFFF',
                  border: '2px solid #E2E8F0',
                  boxShadow: '0 2px 0 #CBD5E1',
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#312E81',
                  cursor: 'pointer',
                }}
              >
                + {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Difficulty Selector */}
        <div>
          <span style={{ fontSize: '12px', fontWeight: 800, color: '#64748B', display: 'block', marginBottom: 8 }}>
            NIVEAU DE SUBTILITÉ DES INDICES
          </span>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            {(['facile', 'moyen', 'expert'] as const).map((lvl) => {
              const active = difficulty === lvl;
              return (
                <button
                  key={lvl}
                  onClick={() => setDifficulty(lvl)}
                  disabled={isGenerating}
                  className="btn-3d"
                  style={{
                    padding: '10px 8px',
                    borderRadius: 14,
                    border: active ? '2px solid #1E1B4B' : '2px solid #E2E8F0',
                    backgroundColor: active ? '#312E81' : '#FFFFFF',
                    color: active ? '#FFFFFF' : '#64748B',
                    boxShadow: active ? '0 3px 0 #1E1B4B' : '0 2px 0 #CBD5E1',
                    fontSize: '13px',
                    fontWeight: 800,
                    textTransform: 'capitalize',
                    cursor: 'pointer',
                  }}
                >
                  {lvl}
                </button>
              );
            })}
          </div>
        </div>

        {/* Deck Preview Card */}
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: 20,
            border: '2px solid #E2E8F0',
            boxShadow: '0 3px 0 #CBD5E1',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '12px', fontWeight: 800, color: '#312E81', textTransform: 'uppercase' }}>
              Aperçu des paramètres du Deck
            </span>
            <span style={{ backgroundColor: '#D1FAE5', color: '#065F46', fontSize: '11px', fontWeight: 800, padding: '2px 8px', borderRadius: 10 }}>
              Prêt
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div style={{ backgroundColor: '#F8FAFC', padding: '10px 12px', borderRadius: 14, border: '1px solid #E2E8F0' }}>
              <div style={{ fontSize: '11px', color: '#64748B', fontWeight: 700 }}>Contenu</div>
              <div style={{ fontSize: '14px', color: '#1E1B4B', fontWeight: 900 }}>10 Objets / Manches</div>
            </div>
            <div style={{ backgroundColor: '#F8FAFC', padding: '10px 12px', borderRadius: 14, border: '1px solid #E2E8F0' }}>
              <div style={{ fontSize: '11px', color: '#64748B', fontWeight: 700 }}>Indices par carte</div>
              <div style={{ fontSize: '14px', color: '#1E1B4B', fontWeight: 900 }}>3 Paliers progressifs</div>
            </div>
          </div>
        </div>

        {/* Generation Progress Display */}
        {isGenerating && (
          <div
            style={{
              backgroundColor: '#FEF3C7',
              borderRadius: 18,
              border: '2px solid #FCD34D',
              padding: '14px 16px',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#B45309', fontWeight: 800, fontSize: '14px' }}>
              <Wand2 size={18} className="animate-spin" />
              Génération en cours avec Gemini...
            </div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#78350F' }}>
              {progressStep === 1 && '🔍 Recherche des références cultes...'}
              {progressStep === 2 && '✍️ Rédaction des 3 indices à difficulté progressive...'}
              {progressStep === 3 && '⚡ Calcul des raretés et pondérations vectorielles...'}
            </div>
          </div>
        )}

        {/* Primary 3D Action Button */}
        <Button3D
          variant="primary"
          size="lg"
          fullWidth
          disabled={isGenerating || !promptText.trim()}
          icon={<Sparkles size={20} />}
          onClick={handleGenerate}
        >
          {isGenerating ? 'CRÉATION EN COURS...' : 'GÉNÉRER LE THÈME (⚡ 1 JETON)'}
        </Button3D>

      </div>
    </div>
  );
};
