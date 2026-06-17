// Central design tokens — keeps every screen visually consistent.
export const colors = {
  bg: '#0B0B10',
  bgElevated: '#131320',
  card: '#16161F',
  cardActive: '#1C1733',
  border: '#23232E',
  text: '#FFFFFF',
  textDim: '#8A8A99',
  textFaint: '#4A4A57',
  accent: '#7C5CFF',
  accentDim: '#2A2150',
  success: '#34D399',
  danger: '#FF5C7A',
  warn: '#FBBF24',
};

export const radius = {
  sm: 10,
  md: 14,
  lg: 20,
  pill: 999,
};

export const spacing = {
  xs: 6,
  sm: 10,
  md: 16,
  lg: 24,
  xl: 36,
};

// Deterministic accent colour for an app's letter badge.
export const BADGE_COLORS = [
  '#7C5CFF',
  '#FF5C7A',
  '#34D399',
  '#FBBF24',
  '#22D3EE',
  '#F472B6',
  '#A78BFA',
  '#4ADE80',
];

export const badgeColor = name => {
  const key = (name || '?').charCodeAt(0) || 0;
  return BADGE_COLORS[key % BADGE_COLORS.length];
};
