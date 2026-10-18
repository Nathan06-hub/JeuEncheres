import React from 'react';
import { Lock, Unlock, Star } from 'lucide-react';
import { DeckItem, ItemRarity } from '../models';

export interface ClueCardProps {
  item: DeckItem;
  revealedCount: number; // 1, 2, or 3
}

export const ClueCard: React.FC<ClueCardProps> = ({ item, revealedCount }) => {
  const getRarityBadge = (rarity: ItemRarity) => {
    switch (rarity) {
      case 'legendary':
        return { label: 'LÉGENDAIRE', bg: '#FEF3C7', color: '#B45309', border: '#FCD34D' };
      case 'epic':
        return { label: 'ÉPIQUE', bg: '#FAF5FF', color: '#7E22CE', border: '#D8B4FE' };
      case 'rare':
        return { label: 'RARE', bg: '#EFF6FF', color: '#1D4ED8', border: '#93C5FD' };
      case 'common':
      default:
        return { label: 'COMMUN', bg: '#F1F5F9', color: '#475569', border: '#CBD5E1' };
    }
  };

  const badge = getRarityBadge(item.rarity);

  const clues = [
    { index: 1, text: item.clue1, isRevealed: revealedCount >= 1, hintLabel: 'Indice #1 • Général' },
    { index: 2, text: item.clue2, isRevealed: revealedCount >= 2, hintLabel: 'Indice #2 • Précis' },
    { index: 3, text: item.clue3, isRevealed: revealedCount >= 3, hintLabel: 'Indice #3 • Décisif' },
  ];

  return (
    <div
      style={{
        backgroundColor: '#FFFFFF',
        borderRadius: 22,
        border: '3px solid #E2E8F0',
        boxShadow: '0 5px 0 #CBD5E1',
        padding: '18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
    >
      {/* Card Header with Mystery Badge & Rarity */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              backgroundColor: '#312E81',
              color: '#FFFFFF',
              fontSize: '11px',
              fontWeight: 900,
              padding: '4px 10px',
              borderRadius: 12,
              letterSpacing: '0.05em',
            }}
          >
            OBJET MYSTÈRE
          </span>
          <span
            style={{
              backgroundColor: badge.bg,
              color: badge.color,
              border: `1.5px solid ${badge.border}`,
              fontSize: '11px',
              fontWeight: 800,
              padding: '3px 8px',
              borderRadius: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 3,
            }}
          >
            <Star size={11} fill={badge.color} />
            {badge.label}
          </span>
        </div>

        <div style={{ fontSize: '13px', fontWeight: 800, color: '#64748B' }}>
          Valeur : <strong style={{ color: '#10B981' }}>{item.score} pts</strong>
        </div>
      </div>

      {/* Clues List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {clues.map((c) => (
          <div
            key={c.index}
            style={{
              borderRadius: 16,
              padding: '12px 14px',
              backgroundColor: c.isRevealed ? '#F8FAFC' : '#F1F5F9',
              border: c.isRevealed ? '2px solid #E2E8F0' : '2px dashed #CBD5E1',
              boxShadow: c.isRevealed ? '0 2px 0 #E2E8F0' : 'none',
              transition: 'all 0.25s ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: '11px', fontWeight: 800, color: c.isRevealed ? '#312E81' : '#94A3B8' }}>
                {c.hintLabel}
              </span>
              {c.isRevealed ? (
                <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: '#10B981', fontSize: '11px', fontWeight: 800 }}>
                  <Unlock size={12} strokeWidth={2.6} /> Révélé
                </span>
              ) : (
                <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: '#94A3B8', fontSize: '11px', fontWeight: 800 }}>
                  <Lock size={12} strokeWidth={2.6} /> Débloqué bientôt
                </span>
              )}
            </div>

            {c.isRevealed ? (
              <p style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#1E1B4B', lineHeight: 1.35 }}>
                « {c.text} »
              </p>
            ) : (
              <p style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: '#94A3B8', fontStyle: 'italic' }}>
                Gardez un œil sur le chrono pour débloquer cet indice clé...
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
