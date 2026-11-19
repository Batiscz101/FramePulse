import type { TextStyle } from 'react-native';

/**
 * Numeric readouts always use tabular figures so values keep a stable width
 * while they change (AGENTS.md rule).
 */
export const tabularNums: TextStyle = { fontVariant: ['tabular-nums'] };

export const palette = {
  canvas: '#09090B',
  surface: '#121215',
  hairline: '#27272A',
  ink: '#FAFAFA',
  muted: '#A1A1AA',
  faint: '#71717A',
  accent: '#9BC7B2',
  grid: '#1E1E22',
} as const;
