import React from 'react';
import { ArrowLeft, Zap } from 'lucide-react';

export interface TopBarProps {
  title?: string;
  showBack?: boolean;
  onBack?: () => void;
  tokensCount: number;
  onTokensClick?: () => void;
  playerName?: string;
  playerLevel?: number;
}

export const TopBar: React.FC<TopBarProps> = ({
  title,
  showBack = false,
  onBack,
  tokensCount,
  onTokensClick,
  playerName = 'Alex',
  playerLevel = 12,
}) => {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 16px',
        backgroundColor: '#FFFFFF',
        borderBottom: '2px solid #E2E8F0',
        position: 'sticky',
        top: 0,
        zIndex: 40,
      }}
    >
      {/* Left side: Back button or Avatar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {showBack ? (
          <button
            onClick={onBack}
            className="btn-3d"
            style={{
              width: 38,
              height: 38,
              borderRadius: 14,
              backgroundColor: '#F1F5F9',
              border: '2px solid #CBD5E1',
              boxShadow: '0 2px 0 #94A3B8',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#1E1B4B',
              cursor: 'pointer',
            }}
          >
            <ArrowLeft size={18} strokeWidth={2.8} />
          </button>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* Player Avatar */}
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: '50%',
                backgroundColor: '#312E81',
                border: '2px solid #1E1B4B',
                boxShadow: '0 2px 0 #1E1B4B',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#FFFFFF',
                fontWeight: 900,
                fontSize: 16,
              }}
            >
              👑
            </div>
            <div>
              <div style={{ fontSize: '15px', fontWeight: 800, color: '#1E1B4B', lineHeight: 1.1 }}>
                {playerName}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                <span
                  style={{
                    backgroundColor: '#EEF2FF',
                    color: '#4F46E5',
                    fontSize: '10px',
                    fontWeight: 800,
                    padding: '1px 6px',
                    borderRadius: 8,
                    border: '1px solid #C7D2FE',
                  }}
                >
                  NIV. {playerLevel}
                </span>
              </div>
            </div>
          </div>
        )}

        {title && (
          <span style={{ fontSize: '17px', fontWeight: 800, color: '#1E1B4B', marginLeft: showBack ? 6 : 0 }}>
            {title}
          </span>
        )}
      </div>

      {/* Right side: Clickable Token Pill */}
      <button
        onClick={onTokensClick}
        className="btn-3d"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          backgroundColor: '#FFFBEB',
          border: '2px solid #FCD34D',
          boxShadow: '0 3px 0 #D97706',
          borderRadius: 20,
          padding: '6px 12px',
          cursor: 'pointer',
        }}
        title="Ouvrir la Boutique de Jetons"
      >
        <div
          style={{
            width: 20,
            height: 20,
            borderRadius: '50%',
            backgroundColor: '#F59E0B',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#FFFFFF',
          }}
        >
          <Zap size={13} fill="#FFFFFF" strokeWidth={0} />
        </div>
        <span style={{ fontSize: '15px', fontWeight: 900, color: '#B45309' }}>
          {tokensCount}
        </span>
        <span
          style={{
            fontSize: '11px',
            fontWeight: 800,
            backgroundColor: '#F59E0B',
            color: '#FFFFFF',
            padding: '1px 5px',
            borderRadius: 8,
            marginLeft: 2,
          }}
        >
          +
        </span>
      </button>
    </header>
  );
};
