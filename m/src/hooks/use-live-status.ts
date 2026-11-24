import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import { useFocusEffect } from 'expo-router';

import { fetchLiveStatus, type LiveStatusRow } from '@/lib/supabase';

/** What the UI consumes – every null field means "not available". */
export type LiveStatus = {
  isPlaying: boolean;
  gameName: string | null;
  processName: string | null;
  startedAt: string | null;
  currentFps: number | null;
  resolution: string | null;
  graphicsApi: string | null;
  gpuTemp: number | null;
  cpuTemp: number | null;
  gpuLoad: number | null;
  cpuLoad: number | null;
};

const POLL_INTERVAL_MS = 6000;
/** The PC agent refreshes the row every few seconds; a margin covers clock offsets. */
const STALE_MS = 90000;

const EMPTY_LIVE_STATUS: LiveStatus = {
  isPlaying: false,
  gameName: null,
  processName: null,
  startedAt: null,
  currentFps: null,
  resolution: null,
  graphicsApi: null,
  gpuTemp: null,
  cpuTemp: null,
  gpuLoad: null,
  cpuLoad: null,
};

function toNullableNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseUpdatedAt(value: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function toLiveStatus(row: LiveStatusRow | null): LiveStatus {
  if (!row || row.is_playing !== true) return EMPTY_LIVE_STATUS;

  const updatedAt = parseUpdatedAt(row.updated_at);
  if (updatedAt !== null && Date.now() - updatedAt.getTime() > STALE_MS) {
    return EMPTY_LIVE_STATUS;
  }

  return {
    isPlaying: true,
    gameName: row.game_name ?? null,
    processName: row.process_name ?? null,
    startedAt: row.started_at ?? null,
    currentFps: toNullableNumber(row.current_fps),
    resolution: row.resolution ?? null,
    graphicsApi: row.graphics_api ?? null,
    gpuTemp: toNullableNumber(row.gpu_temp),
    cpuTemp: toNullableNumber(row.cpu_temp),
    gpuLoad: toNullableNumber(row.gpu_load),
    cpuLoad: toNullableNumber(row.cpu_load),
  };
}

/**
 * Reads the `live_status` row (id = 'default') of the PC agent. It refreshes
 * when the screen is focused and then every 6 s while the app is in the
 * foreground; when the app goes to the background or the screen is unfocused,
 * the polling stops to save battery and mobile data, and it resumes immediately
 * on return.
 */
export function useLiveStatus(): LiveStatus {
  const [status, setStatus] = useState<LiveStatus>(EMPTY_LIVE_STATUS);
  const [appState, setAppState] = useState<AppStateStatus>((AppState.currentState ?? 'active') as AppStateStatus);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (next) => setAppState(next));
    return () => subscription.remove();
  }, []);

  const refresh = useCallback(async () => {
    try {
      const row = await fetchLiveStatus();

      if (!mounted.current) return;
      const next = toLiveStatus(row);
      // Keep the same object identity when nothing changed to avoid rerenders.
      setStatus((current) => (current === next ? current : next));
    } catch {
      // Transient network errors keep the last known status.
    }
  }, []);

  // Poll only while the app is in the foreground; the focus effect refreshes
  // immediately when the app/screen returns to the foreground.
  const pollingActive = appState === 'active';

  useEffect(() => {
    if (!pollingActive) return undefined;
    const interval = setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [pollingActive, refresh]);

  useFocusEffect(
    useCallback(() => {
      void refresh();
    }, [refresh]),
  );

  return status;
}
