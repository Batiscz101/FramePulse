import { useCallback, useEffect, useState } from 'react';

import { useOnReconnect } from '@/hooks/use-reconnect';
import { useI18n } from '@/lib/i18n-context';
import { cacheSamples, readCachedSamples } from '@/lib/offline-cache';
import { describeError, fetchSessionSamples } from '@/lib/telemetry-api';
import type { FpsSample } from '@/types/telemetry';

import type { LoadState } from '@/hooks/use-games';

/**
 * Finished sessions never change, so their (already downsampled) series can be
 * kept for the lifetime of the app and switching days is instant. A copy also
 * lives in AsyncStorage so charts open without a connection.
 */
const sampleCache = new Map<string, FpsSample[]>();

/**
 * Returns the samples of a session already loaded this session run
 * (finished sessions never change), or null. Used to open the session-compare
 * view and history instantly.
 */
export function getCachedSamples(sessionId: string): FpsSample[] | null {
  return sampleCache.get(sessionId) ?? null;
}

/** Loads the FPS series of the selected session. */
export function useSessionSamples(sessionId: string | undefined) {
  const { language } = useI18n();
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ id: string; error: unknown } | null>(null);
  const [offlineId, setOfflineId] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!sessionId) return;

    const requestId = sessionId;
    let cancelled = false;

    // Memory copy: the series is already loaded and rendered from `cached`
    // below, so there is nothing to synchronously update.
    if (sampleCache.has(requestId)) return;

    const load = async () => {
      const cached = await readCachedSamples(requestId);
      if (cancelled) return;

      if (cached) {
        sampleCache.set(requestId, cached.data);
        setLoadedId(requestId);
        setLastSync(cached.savedAt);
      }

      try {
        const next = await fetchSessionSamples(requestId);
        if (cancelled) return;

        sampleCache.set(requestId, next);
        setLoadedId(requestId);
        setFailure((current) => (current?.id === requestId ? null : current));
        setOfflineId((current) => (current === requestId ? null : current));

        const savedAt = await cacheSamples(requestId, next);
        if (!cancelled) setLastSync(savedAt);
      } catch (caught) {
        if (cancelled) return;

        if (sampleCache.has(requestId)) {
          // Offline: the saved chart is still browsable.
          setLoadedId(requestId);
          setOfflineId(requestId);
          setFailure((current) => (current?.id === requestId ? null : current));
        } else {
          setFailure({ id: requestId, error: caught });
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [sessionId, attempt]);

  const reload = useCallback(() => {
    // Drop the in-memory copy so the next attempt really hits the network.
    if (sessionId) sampleCache.delete(sessionId);
    setAttempt((value) => value + 1);
  }, [sessionId]);

  // Background refresh once connectivity is back after an offline load.
  useOnReconnect(() => {
    if (offlineId === sessionId && sessionId) reload();
  });

  if (!sessionId) {
    return {
      samples: [] as FpsSample[],
      state: 'ready' as LoadState,
      error: null,
      offline: false,
      lastSync: null,
      reload,
    };
  }

  if (failure?.id === sessionId) {
    return {
      samples: [] as FpsSample[],
      state: 'error' as LoadState,
      error: describeError(failure.error, language),
      offline: false,
      lastSync,
      reload,
    };
  }

  const cached = sampleCache.get(sessionId);
  const ready = loadedId === sessionId || cached !== undefined;

  return {
    samples: ready ? (cached ?? []) : ([] as FpsSample[]),
    state: (ready ? 'ready' : 'loading') as LoadState,
    error: null,
    offline: offlineId === sessionId,
    lastSync,
    reload,
  };
}
