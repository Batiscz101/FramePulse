import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';

import { supabase } from '@/lib/supabase';

/** Row of the `live_status` table as written by the PC agent (v1.2.0). */
export type LiveStatusRow = {
  id: string;
  is_playing: boolean;
  game_name: string | null;
  process_name: string | null;
  started_at: string | null;
  current_fps: number | string | null;
  resolution: string | null;
  graphics_api: string | null;
  gpu_temp: number | string | null;
  cpu_temp: number | string | null;
  updated_at: string | null;
};

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
};

const POLL_INTERVAL_MS = 6000;
/** The PC agent refreshes the row every 8 s; ignore older rows while not playing. */
const STALE_MS = 45000;

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
};

function toNullableNumber(value: number | string | null): number | null {
  if (value === null || value === '') return null;
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
  };
}

/**
 * Reads the `live_status` row (id = 'default') of the PC agent. It refreshes
 * when the screen is focused and then every 6 s while the app is in the
 * foreground; the polling stops as soon as the screen is unfocused.
 */
export function useLiveStatus(): LiveStatus {
  const [status, setStatus] = useState<LiveStatus>(EMPTY_LIVE_STATUS);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    try {
      const { data } = await supabase
        .from('live_status')
        .select('*')
        .eq('id', 'default')
        .maybeSingle();

      if (!mounted.current) return;
      setStatus(toLiveStatus(data as LiveStatusRow | null));
    } catch {
      // Transient network errors keep the last known status.
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void refresh();
      const interval = setInterval(() => {
        void refresh();
      }, POLL_INTERVAL_MS);
      return () => clearInterval(interval);
    }, [refresh]),
  );

  return status;
}
