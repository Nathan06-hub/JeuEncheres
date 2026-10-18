import React from 'react';
import { Home, Sparkles, Flame, Trophy, ShoppingBag } from 'lucide-react';
import { ScreenId } from '../models';

export interface BottomNavBarProps {
  activeScreen: ScreenId;
  onNavigate: (screen: ScreenId) => void;
}

export const BottomNavBar: React.FC<BottomNavBarProps> = ({
  activeScreen,
  onNavigate,
}) => {
  const navItems: { id: ScreenId; label: string; icon: React.ReactNode }[] = [
    { id: 'home', label: 'Accueil', icon: <Home size={20} strokeWidth={2.6} /> },
    { id: 'creation', label: 'Créer IA', icon: <Sparkles size={20} strokeWidth={2.6} /> },
    { id: 'auction', label: 'Enchères', icon: <Flame size={20} strokeWidth={2.6} /> },
    { id: 'results', label: 'Résultats', icon: <Trophy size={20} strokeWidth={2.6} /> },
    { id: 'shop', label: 'Boutique', icon: <ShoppingBag size={20} strokeWidth={2.6} /> },
  ];

  return (
    <nav
      style={{
        position: 'sticky',
        bottom: 0,
        backgroundColor: '#FFFFFF',
        borderTop: '2px solid #E2E8F0',
        padding: '8px 12px 14px',
        display: 'flex',
        justifyContent: 'space-around',
        alignItems: 'center',
        zIndex: 50,
      }}
    >
      {navItems.map((item) => {
        const isActive = activeScreen === item.id;
        return (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 3,
              backgroundColor: isActive ? '#EEF2FF' : 'transparent',
              border: isActive ? '2px solid #C7D2FE' : '2px solid transparent',
              boxShadow: isActive ? '0 2px 0 #818CF8' : 'none',
              borderRadius: 16,
              padding: '6px 12px',
              cursor: 'pointer',
              color: isActive ? '#312E81' : '#94A3B8',
              transition: 'all 0.15s ease',
              minWidth: 58,
            }}
          >
            <div style={{ transform: isActive ? 'scale(1.1)' : 'scale(1)', transition: 'transform 0.15s ease' }}>
              {item.icon}
            </div>
            <span
              style={{
                fontSize: '11px',
                fontWeight: isActive ? 800 : 600,
                color: isActive ? '#312E81' : '#64748B',
              }}
            >
              {item.label}
            </span>
          </button>
        );
      })}
    </nav>
  );
};
