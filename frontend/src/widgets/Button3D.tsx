import React from 'react';

export interface Button3DProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'success' | 'danger' | 'secondary' | 'neutral' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

export const Button3D: React.FC<Button3DProps> = ({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  icon,
  children,
  className = '',
  disabled,
  style,
  onMouseDown,
  onMouseUp,
  onMouseLeave,
  onTouchStart,
  onTouchEnd,
  ...props
}) => {
  const getVariantStyles = () => {
    if (disabled) {
      return {
        bg: '#E2E8F0',
        color: '#94A3B8',
        shadow: '#CBD5E1',
        border: '#CBD5E1',
      };
    }
    switch (variant) {
      case 'primary': // Jaune ambré / moutarde éclatant
        return {
          bg: '#F59E0B',
          color: '#FFFFFF',
          shadow: '#B45309',
          border: '#D97706',
        };
      case 'success': // Vert pomme franc
        return {
          bg: '#10B981',
          color: '#FFFFFF',
          shadow: '#047857',
          border: '#059669',
        };
      case 'danger': // Corail / rose énergique
        return {
          bg: '#F43F5E',
          color: '#FFFFFF',
          shadow: '#BE123C',
          border: '#E11D48',
        };
      case 'secondary': // Indigo profond / aubergine
        return {
          bg: '#312E81',
          color: '#FFFFFF',
          shadow: '#1E1B4B',
          border: '#3730A3',
        };
      case 'neutral': // Blanc / relief doux
        return {
          bg: '#FFFFFF',
          color: '#1E1B4B',
          shadow: '#CBD5E1',
          border: '#E2E8F0',
        };
      case 'ghost':
        return {
          bg: 'transparent',
          color: '#312E81',
          shadow: 'transparent',
          border: 'transparent',
        };
      default:
        return {
          bg: '#F59E0B',
          color: '#FFFFFF',
          shadow: '#B45309',
          border: '#D97706',
        };
    }
  };

  const getSizeStyles = () => {
    switch (size) {
      case 'sm':
        return {
          padding: '8px 14px',
          fontSize: '13px',
          shadowDepth: '3px',
          activeTranslate: '2px',
          radius: '14px',
        };
      case 'lg':
        return {
          padding: '16px 24px',
          fontSize: '17px',
          shadowDepth: '5px',
          activeTranslate: '4px',
          radius: '20px',
        };
      case 'md':
      default:
        return {
          padding: '12px 20px',
          fontSize: '15px',
          shadowDepth: '4px',
          activeTranslate: '3px',
          radius: '18px',
        };
    }
  };

  const v = getVariantStyles();
  const s = getSizeStyles();

  const handlePressDown = (e: React.MouseEvent<HTMLButtonElement> | React.TouchEvent<HTMLButtonElement>) => {
    if (!disabled && variant !== 'ghost') {
      e.currentTarget.style.transform = `translateY(${s.activeTranslate})`;
      e.currentTarget.style.boxShadow = `0 1px 0 ${v.shadow}`;
    }
  };

  const handlePressUp = (e: React.MouseEvent<HTMLButtonElement> | React.TouchEvent<HTMLButtonElement>) => {
    if (!disabled && variant !== 'ghost') {
      e.currentTarget.style.transform = 'translateY(0)';
      e.currentTarget.style.boxShadow = `0 ${s.shadowDepth} 0 ${v.shadow}`;
    }
  };

  return (
    <button
      {...props}
      disabled={disabled}
      className={`btn-3d flex items-center justify-center font-extrabold select-none transition-all ${className}`}
      style={{
        width: fullWidth ? '100%' : 'auto',
        backgroundColor: v.bg,
        color: v.color,
        border: `2px solid ${v.border}`,
        borderRadius: s.radius,
        padding: s.padding,
        fontSize: s.fontSize,
        boxShadow: disabled ? 'none' : `0 ${s.shadowDepth} 0 ${v.shadow}`,
        cursor: disabled ? 'not-allowed' : 'pointer',
        transform: 'translateY(0)',
        lineHeight: 1.2,
        letterSpacing: '0.01em',
        ...style,
      }}
      onMouseDown={(e) => {
        handlePressDown(e);
        onMouseDown?.(e);
      }}
      onMouseUp={(e) => {
        handlePressUp(e);
        onMouseUp?.(e);
      }}
      onMouseLeave={(e) => {
        handlePressUp(e);
        onMouseLeave?.(e);
      }}
      onTouchStart={(e) => {
        handlePressDown(e);
        onTouchStart?.(e);
      }}
      onTouchEnd={(e) => {
        handlePressUp(e);
        onTouchEnd?.(e);
      }}
    >
      {icon && <span style={{ marginRight: children ? 8 : 0, display: 'inline-flex' }}>{icon}</span>}
      {children}
    </button>
  );
};
