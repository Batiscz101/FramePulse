import { vars } from 'nativewind';
import type { TextStyle } from 'react-native';

/**
 * Numeric readouts always use tabular figures so values keep a stable width
 * while they change (AGENTS.md rule).
 */
export const tabularNums: TextStyle = { fontVariant: ['tabular-nums'] };

export const THEME_MODES = ['dark', 'light'] as const;

export type ThemeMode = (typeof THEME_MODES)[number];

export const DEFAULT_THEME_MODE: ThemeMode = 'dark';

/**
 * Semantic colours shared by the Tailwind classes (through CSS variables) and
 * by code that needs real values (chart, spinners, icons).
 */
export type ThemePalette = {
  canvas: string;
  surface: string;
  raised: string;
  hairline: string;
  ink: string;
  muted: string;
  faint: string;
  accent: string;
  grid: string;
  strip: string;
  tooltip: string;
  tooltipBorder: string;
  danger: string;
  onInkMuted: string;
};

/** The original minimalist dark theme, kept exactly as before. */
const DARK: ThemePalette = {
  canvas: '#09090B',
  surface: '#121215',
  raised: '#18181C',
  hairline: '#27272A',
  ink: '#FAFAFA',
  muted: '#A1A1AA',
  faint: '#71717A',
  accent: '#9BC7B2',
  grid: '#1E1E22',
  strip: '#3F3F46',
  tooltip: '#1C1C20',
  tooltipBorder: '#3F3F46',
  danger: '#F87171',
  onInkMuted: '#52525B',
};

/** Light counterpart – same restraint, no gradients or neon accents. */
const LIGHT: ThemePalette = {
  canvas: '#F8FAFC',
  surface: '#FFFFFF',
  raised: '#F4F4F5',
  hairline: '#E4E4E7',
  ink: '#09090B',
  muted: '#52525B',
  faint: '#71717A',
  accent: '#4F8F76',
  grid: '#F1F5F9',
  strip: '#D4D4D8',
  tooltip: '#FFFFFF',
  tooltipBorder: '#E4E4E7',
  danger: '#DC2626',
  onInkMuted: '#A1A1AA',
};

export const palettes: Record<ThemeMode, ThemePalette> = {
  dark: DARK,
  light: LIGHT,
};

/** Maps palette keys to the CSS variables declared in tailwind.config.js. */
const CSS_VARIABLES: Record<keyof ThemePalette, `--color-${string}`> = {
  canvas: '--color-canvas',
  surface: '--color-surface',
  raised: '--color-raised',
  hairline: '--color-hairline',
  ink: '--color-ink',
  muted: '--color-muted',
  faint: '--color-faint',
  accent: '--color-accent',
  grid: '--color-grid',
  strip: '--color-strip',
  tooltip: '--color-tooltip',
  tooltipBorder: '--color-tooltip-border',
  danger: '--color-danger',
  onInkMuted: '--color-on-ink-muted',
};

/** `#09090B` -> `9 9 11` (the format NativeWind expects for `rgb(var(...))`). */
function toRgbChannels(hex: string): string {
  const value = hex.replace('#', '');
  const red = Number.parseInt(value.slice(0, 2), 16);
  const green = Number.parseInt(value.slice(2, 4), 16);
  const blue = Number.parseInt(value.slice(4, 6), 16);
  return `${red} ${green} ${blue}`;
}

/** Style for the theme root – defines every `--color-*` variable at once. */
export function themeVariables(mode: ThemeMode): ReturnType<typeof vars> {
  const palette = palettes[mode];
  const variables: Record<string, string> = {};

  for (const key of Object.keys(palette) as (keyof ThemePalette)[]) {
    variables[CSS_VARIABLES[key]] = toRgbChannels(palette[key]);
  }

  return vars(variables);
}

export function isThemeMode(value: unknown): value is ThemeMode {
  return typeof value === 'string' && (THEME_MODES as readonly string[]).includes(value);
}
