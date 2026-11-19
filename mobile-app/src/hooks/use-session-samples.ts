import { useEffect, useState } from 'react';

import { useI18n } from '@/lib/i18n-context';
import { describeError, fetchSessionSamples } from '@/lib/telemetry-api';
import type { FpsSample } from '@/types/telemetry';

import type { LoadState } from '@/hooks/use-games';

/**
 * Finished sessions never change, so their (already downsampled) series can be
 * kept for the lifetime of the app and switching days is instant.
 */
const sampleCache = new Map<string, FpsSample[]>();

/** Loads the FPS series of the selected session. */
export function useSessionSamples(sessionId: string | undefined) {
  const { language } = useI18n();
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ id: string; error: unknown } | null>(null);

  useEffect(() => {
    if (!sessionId || sampleCache.has(sessionId)) return;

    let cancelled = false;

    fetchSessionSamples(sessionId)
      .then((next) => {
        if (cancelled) return;
        sampleCache.set(sessionId, next);
        setLoadedId(sessionId);
      })
      .catch((caught) => {
        if (cancelled) return;
        setFailure({ id: sessionId, error: caught });
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (!sessionId) {
    return { samples: [] as FpsSample[], state: 'ready' as LoadState, error: null };
  }

  if (failure?.id === sessionId) {
    return {
      samples: [] as FpsSample[],
      state: 'error' as LoadState,
      error: describeError(failure.error, language),
    };
  }

  const cached = sampleCache.get(sessionId);
  const ready = loadedId === sessionId || cached !== undefined;

  return {
    samples: ready ? (cached ?? []) : ([] as FpsSample[]),
    state: (ready ? 'ready' : 'loading') as LoadState,
    error: null,
  };
}
