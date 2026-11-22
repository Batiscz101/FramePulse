/** Per-session statistics used by the session comparison (v1.2.0). */

import type { FpsSample, GameSession } from '@/types/telemetry';

export type SessionStats = {
  avgFps: number;
  /** 1% low as stored in the database (the PC agent reports the 1% low as `min_fps`). */
  low1: number;
  /** 0.1% low, computed from the session samples when available. */
  low01: number | null;
  /** Average frame time in ms (`1000 / avg_fps`). */
  frameTimeMs: number | null;
  gpuTempAvg: number | null;
  gpuTempMax: number | null;
  gpuLoadAvg: number | null;
  cpuTempAvg: number | null;
  cpuLoadAvg: number | null;
};

/**
 * Approximates the 0.1% low: the average of the worst 0.1 % of frame times,
 * converted back to FPS (the same definition as the 1% low in the PC agent).
 */
export function computeZeroPointOneLows(samples: FpsSample[]): number | null {
  if (samples.length === 0) return null;

  const frameTimes = samples
    .map((sample) => (sample.fps > 0 ? 1000 / sample.fps : 0))
    .sort((a, b) => b - a);
  const count = Math.max(1, Math.ceil(frameTimes.length * 0.001));

  let total = 0;
  for (let index = 0; index < count; index += 1) total += frameTimes[index];

  const meanFrameTime = total / count;
  if (!(meanFrameTime > 0)) return null;
  return 1000 / meanFrameTime;
}

export function computeSessionStats(
  session: GameSession,
  samples: FpsSample[] | null,
): SessionStats {
  return {
    avgFps: session.avgFps,
    low1: session.minFps,
    low01: computeZeroPointOneLows(samples ?? []),
    frameTimeMs: session.avgFps > 0 ? 1000 / session.avgFps : null,
    gpuTempAvg: session.gpuTempAvg ?? null,
    gpuTempMax: session.gpuTempMax ?? null,
    gpuLoadAvg: session.gpuLoadAvg ?? null,
    cpuTempAvg: session.cpuTempAvg ?? null,
    cpuLoadAvg: session.cpuLoadAvg ?? null,
  };
}

/**
 * Relative difference between `a` (A) and `b` (B): `+18.4%` / `−3.2 ms` style.
 * Percent mode is used for ratios (FPS, Lows, frame time %, temps) and plain
 * unit mode for absolute values (frame time ms, temperatures, loads).
 */
export function formatDiff(
  a: number,
  b: number,
  options: { percent?: boolean; unit?: string },
): string {
  const delta = b - a;
  const magnitude = Math.abs(a) > 0 ? Math.abs(a) : 1;
  const percent = (Math.abs(delta) / magnitude) * 100;
  const sign = delta > 0 ? '+' : '−';

  if (options.percent) return `${sign}${percent.toFixed(1)}%`;

  return `${sign}${Math.abs(delta).toFixed(1)}${options.unit ?? ''}`;
}

/**
 * Colors a difference for a metric: `colors.accent` (green) when `b` is better
 * than `a`, `colors.danger` (red) when it is worse.
 */
export function diffColor(
  a: number,
  b: number,
  better: 'up' | 'down',
  colors: { accent: string; danger: string },
): string {
  const improved = better === 'up' ? b > a : b < a;
  return improved ? colors.accent : colors.danger;
}
