export const colors = {
  background: '#F7F9FD',
  surface: '#FFFFFF',
  surfaceSoft: '#F1F5F9',
  surfaceTint: '#EEF2FF',

  // Primaire / Actions fortes (Jaune ambré / moutarde éclatant)
  primary: {
    main: '#F59E0B',
    hover: '#D97706',
    shadow: '#B45309',
    light: '#FEF3C7',
    text: '#78350F',
  },

  // Secondaire / Structure (Indigo profond / aubergine)
  secondary: {
    main: '#312E81',
    dark: '#1E1B4B',
    light: '#E0E7FE',
    muted: '#4F46E5',
    text: '#1E1B4B',
  },

  // Validation / Enchères (Vert pomme franc)
  success: {
    main: '#10B981',
    hover: '#059669',
    shadow: '#047857',
    light: '#D1FAE5',
    text: '#065F46',
  },

  // Alertes / Timer / Malus (Corail / rose énergique)
  danger: {
    main: '#F43F5E',
    hover: '#E11D48',
    shadow: '#BE123C',
    light: '#FFE4E6',
    text: '#9F1239',
  },

  // Neutres & Bordures
  neutral: {
    50: '#F8FAFC',
    100: '#F1F5F9',
    200: '#E2E8F0',
    300: '#CBD5E1',
    400: '#94A3B8',
    500: '#64748B',
    600: '#475569',
    700: '#334155',
    800: '#1E293B',
    900: '#0F172A',
  },

  rarity: {
    common: { bg: '#F1F5F9', text: '#475569', border: '#CBD5E1', label: 'COMMUN' },
    rare: { bg: '#EFF6FF', text: '#2563EB', border: '#93C5FD', label: 'RARE' },
    epic: { bg: '#FAF5FF', text: '#9333EA', border: '#D8B4FE', label: 'ÉPIQUE' },
    legendary: { bg: '#FFFBEB', text: '#D97706', border: '#FCD34D', label: 'LÉGENDAIRE' },
  },
} as const;
