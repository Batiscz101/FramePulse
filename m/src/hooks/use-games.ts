import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';

import { useOnReconnect } from '@/hooks/use-reconnect';
import { useI18n } from '@/lib/i18n-context';
import { cacheGames, readCachedGames } from '@/lib/offline-cache';
import { describeError, fetchGames } from '@/lib/telemetry-api';
import type { Game } from '@/types/telemetry';

export type LoadState = 'loading' | 'ready' | 'error';

/**
 * Loads the game list once and refreshes it whenever the screen is focused
 * (so a rename or a new session on the PC shows up immediately).
 *
 * Every successful read is cached locally. When Supabase is unreachable the
 * cached list is shown instead of an error screen and refreshed as soon as the
 * connection returns.
 */
export function useGames() {
  const { language } = useI18n();
  const [games, setGames] = useState<Game[]>([]);
  const [state, setState] = useState<LoadState>('loading');
  const [failure, setFailure] = useState<unknown>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [offline, setOffline] = useState(false);
  const [lastSync, setLastSync] = useState<number | null>(null);

  const mounted = useRef(true);
  const hasLoaded = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(async (mode: 'focus' | 'refresh') => {
    if (mode === 'refresh') setRefreshing(true);

    // Open instantly with the saved list; the network request follows.
    if (!hasLoaded.current) {
      const cached = await readCachedGames();
      if (!mounted.current) return;

      if (cached && cached.data.length > 0) {
        setGames(cached.data);
        setState('ready');
        setLastSync(cached.savedAt);
      }
    }

    try {
      const next = await fetchGames();
      if (!mounted.current) return;

      hasLoaded.current = true;
      setGames(next);
      setFailure(null);
      setState('ready');
      setOffline(false);

      const savedAt = await cacheGames(next);
      if (mounted.current) setLastSync(savedAt);
    } catch (caught) {
      if (!mounted.current) return;

      const cached = await readCachedGames();
      if (!mounted.current) return;

      if (cached) {
        // Offline browsing: keep the saved data, no error screen.
        setGames(cached.data);
        setLastSync(cached.savedAt);
        setFailure(null);
        setState('ready');
        setOffline(true);
      } else {
        setFailure(caught);
        setOffline(false);
        // Keep showing the last successful data instead of an empty screen.
        setState(hasLoaded.current ? 'ready' : 'error');
      }
    } finally {
      if (mounted.current) setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load('focus');
    }, [load]),
  );

  // Background refresh once connectivity is back after an offline load.
  useOnReconnect(() => {
    if (offline) void load('focus');
  });

  const refresh = useCallback(() => {
    void load('refresh');
  }, [load]);

  return {
    games,
    state,
    error: failure ? describeError(failure, language) : null,
    refreshing,
    refresh,
    offline,
    lastSync,
  };
}
