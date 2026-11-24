import type { FpsSample } from '@/types/telemetry';

import { downsampleSamples } from '@/types/telemetry';

/** Max points rendered per chart (PresentMon sessions can have thousands). */
export const CHART_MAX_POINTS = 70;

/**
 * Keeps the points where `key` has a usable value. Charts pass the filtered
 * arrays to `react-native-gifted-charts` so a null sample never breaks the
 * curve or throws when a tooltip touches it.
 */
export function filterSamples(samples: FpsSample[], key: keyof FpsSample): FpsSample[] {
  return samples.filter((sample) => {
    const value = sample[key];
    return typeof value === 'number' && Number.isFinite(value);
  });
}

/** Reduces the series to at most `CHART_MAX_POINTS` readable points. */
export function reduceSamples(samples: FpsSample[]): FpsSample[] {
  return downsampleSamples(samples, CHART_MAX_POINTS);
}
