import React from 'react';

export interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  variant?: 'primary' | 'success' | 'danger' | 'secondary' | 'neutral';
  highlight?: boolean;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  variant = 'neutral',
  highlight = false,
}) => {
  const getColors = () => {
    switch (variant) {
      case 'primary':
        return { bg: '#FEF3C7', text: '#B45309', border: '#FCD34D' };
      case 'success':
        return { bg: '#D1FAE5', text: '#065F46', border: '#6EE7B7' };
      case 'danger':
        return { bg: '#FFE4E6', text: '#9F1239', border: '#FDA4AF' };
      case 'secondary':
        return { bg: '#EEF2FF', text: '#312E81', border: '#C7D2FE' };
      case 'neutral':
      default:
        return { bg: '#FFFFFF', text: '#1E1B4B', border: '#E2E8F0' };
    }
  };

  const c = getColors();

  return (
    <div
      style={{
        backgroundColor: c.bg,
        border: `2px solid ${c.border}`,
        borderRadius: '18px',
        padding: '14px 16px',
        boxShadow: highlight ? '0 4px 0 #CBD5E1' : '0 2px 0 #E2E8F0',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: '12px', fontWeight: 700, color: '#64748B', textTransform: 'uppercase' }}>
          {title}
        </span>
        {icon && <span style={{ color: c.text }}>{icon}</span>}
      </div>
      <div style={{ fontSize: '22px', fontWeight: 900, color: c.text, lineHeight: 1.1 }}>
        {value}
      </div>
      {subtitle && (
        <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748B', marginTop: 4 }}>
          {subtitle}
        </div>
      )}
    </div>
  );
};
