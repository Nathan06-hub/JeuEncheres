import React from 'react';

export interface PillChipProps {
  label: string;
  icon?: React.ReactNode;
  isActive?: boolean;
  onClick?: () => void;
  count?: number | string;
  badge?: string;
  size?: 'sm' | 'md';
}

export const PillChip: React.FC<PillChipProps> = ({
  label,
  icon,
  isActive = false,
  onClick,
  count,
  badge,
  size = 'md',
}) => {
  return (
    <button
      onClick={onClick}
      className="pill-chip select-none flex items-center gap-2 whitespace-nowrap transition-all font-bold"
      style={{
        padding: size === 'sm' ? '6px 12px' : '9px 16px',
        borderRadius: '24px',
        fontSize: size === 'sm' ? '12px' : '14px',
        backgroundColor: isActive ? '#312E81' : '#FFFFFF',
        color: isActive ? '#FFFFFF' : '#312E81',
        border: isActive ? '2px solid #1E1B4B' : '2px solid #E2E8F0',
        boxShadow: isActive ? '0 3px 0 #1E1B4B' : '0 2px 0 #CBD5E1',
        cursor: 'pointer',
        transform: 'translateY(0)',
      }}
      onMouseDown={(e) => {
        e.currentTarget.style.transform = 'translateY(2px)';
        e.currentTarget.style.boxShadow = '0 0px 0 transparent';
      }}
      onMouseUp={(e) => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = isActive ? '0 3px 0 #1E1B4B' : '0 2px 0 #CBD5E1';
      }}
    >
      {icon && <span className="flex items-center text-sm">{icon}</span>}
      <span>{label}</span>
      {count !== undefined && (
        <span
          style={{
            backgroundColor: isActive ? '#4F46E5' : '#F1F5F9',
            color: isActive ? '#FFFFFF' : '#64748B',
            padding: '2px 7px',
            borderRadius: '12px',
            fontSize: '11px',
            fontWeight: 800,
          }}
        >
          {count}
        </span>
      )}
      {badge && (
        <span
          style={{
            backgroundColor: '#F59E0B',
            color: '#FFFFFF',
            padding: '2px 6px',
            borderRadius: '10px',
            fontSize: '10px',
            fontWeight: 800,
          }}
        >
          {badge}
        </span>
      )}
    </button>
  );
};
