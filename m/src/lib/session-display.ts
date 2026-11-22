/** Display helpers for the game-facts and telemetry columns (v1.2.0). */

import type { GameSession } from '@/types/telemetry';

/** `2560x1440` -> `2560×1440` (the typography's narrow multiplication sign). */
export function formatResolution(value: string | null | undefined): string | null {
  if (!value) return null;
  return value.replace(/[xX]/, '×');
}

export function formatDisplayMode(value: string | null | undefined): string | null {
  return value && value.length > 0 ? value : null;
}

export function formatGraphicsApi(value: string | null | undefined): string | null {
  return value && value.length > 0 ? value : null;
}

/** `48.2` -> `48°C` (whole degrees, as the PC agent reports them). */
export function formatTempC(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${Math.round(value)}°C`;
}

export function formatPercent(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${Math.round(value)}%`;
}

export function formatFpsLimit(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value) || !(value > 0)) {
    return null;
  }
  return String(Math.round(value));
}

/** On/Off of boolean settings (technical values, no per-language change needed). */
export function formatFlag(value: boolean | null | undefined): string | null {
  if (value === true) return 'On';
  if (value === false) return 'Off';
  return null;
}

export type GameSettingRow = {
  /** Translation key of the row label. */
  labelKey:
    | 'badgeQualityPreset'
    | 'badgeDlss'
    | 'badgeFsr'
    | 'badgeRayTracing'
    | 'badgeVsync'
    | 'badgeFpsLimit';
  value: string | null;
};

/** The non-null key graphics settings of the session (PC agent v1.2.0). */
export function gameSettingRows(session: GameSession): GameSettingRow[] {
  const settings = session.gameSettings;
  if (!settings) return [];

  const rows: GameSettingRow[] = [];

  if (typeof settings.quality === 'string' && settings.quality.length > 0) {
    rows.push({ labelKey: 'badgeQualityPreset', value: settings.quality });
  }
  if (settings.dlss != null) rows.push({ labelKey: 'badgeDlss', value: formatFlag(settings.dlss) });
  if (settings.fsr != null) rows.push({ labelKey: 'badgeFsr', value: formatFlag(settings.fsr) });
  if (settings.ray_tracing != null) {
    rows.push({ labelKey: 'badgeRayTracing', value: formatFlag(settings.ray_tracing) });
  }
  if (settings.vsync != null) rows.push({ labelKey: 'badgeVsync', value: formatFlag(settings.vsync) });

  const fpsLimit = typeof settings.fps_limit === 'number' ? settings.fps_limit : null;
  if (fpsLimit !== null) rows.push({ labelKey: 'badgeFpsLimit', value: formatFpsLimit(fpsLimit) });

  return rows;
}
