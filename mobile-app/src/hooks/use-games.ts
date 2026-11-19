import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';

import { useI18n } from '@/lib/i18n-context';
import { describeError, fetchGames } from '@/lib/telemetry-api';
import type { Game } from '@/types/telemetry';

export type LoadState = 'loading' | 'ready' | 'error';

/**
 * Loads the game list once and refreshes it whenever the screen is focused
 * (so a rename or a new session on the PC shows up immediately).
 */
export function useGames() {
  const { language } = useI18n();
  const [games, setGames] = useState<Game[]>([]);
  const [state, setState] = useState<LoadState>('loading');
  const [failure, setFailure] = useState<unknown>(null);
  const [refreshing, setRefreshing] = useState(false);

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

    try {
      const next = await fetchGames();
      if (!mounted.current) return;

      hasLoaded.current = true;
      setGames(next);
      setFailure(null);
      setState('ready');
    } catch (caught) {
      if (!mounted.current) return;

      setFailure(caught);
      // Keep showing the last successful data instead of an empty screen.
      setState(hasLoaded.current ? 'ready' : 'error');
    } finally {
      if (mounted.current) setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load('focus');
    }, [load]),
  );

  const refresh = useCallback(() => {
    void load('refresh');
  }, [load]);

  return {
    games,
    state,
    error: failure ? describeError(failure, language) : null,
    refreshing,
    refresh,
  };
}
