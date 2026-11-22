import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';

import { useOnReconnect } from '@/hooks/use-reconnect';
import { useI18n } from '@/lib/i18n-context';
import { cacheGame, readCachedGame } from '@/lib/offline-cache';
import { describeError, fetchGame, renameGame } from '@/lib/telemetry-api';
import { shortNameFor, type Game } from '@/types/telemetry';

import type { LoadState } from '@/hooks/use-games';

/**
 * Loads a single game (with sessions) and exposes a rename action. The cached
 * copy is shown immediately and kept on screen when the database is
 * unreachable.
 */
export function useGame(gameId: string | undefined) {
  const { language, t } = useI18n();
  const [game, setGame] = useState<Game | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [failure, setFailure] = useState<unknown>(null);
  const [offline, setOffline] = useState(false);
  const [lastSync, setLastSync] = useState<number | null>(null);

  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    if (!gameId) return;

    // Prefill from the cache so the detail opens instantly (and offline).
    const cached = await readCachedGame(gameId);
    if (!mounted.current) return;

    if (cached) {
      setGame(cached.data);
      setState('ready');
      setLastSync(cached.savedAt);
    }

    try {
      const next = await fetchGame(gameId);
      if (!mounted.current) return;

      if (!next) {
        setGame(null);
        setFailure(null);
        setState('error');
        setOffline(false);
        return;
      }

      setGame(next);
      setFailure(null);
      setState('ready');
      setOffline(false);

      const savedAt = await cacheGame(next);
      if (mounted.current) setLastSync(savedAt);
    } catch (caught) {
      if (!mounted.current) return;

      if (cached) {
        setGame(cached.data);
        setFailure(null);
        setState('ready');
        setOffline(true);
      } else {
        setFailure(caught);
        setState('error');
        setOffline(false);
      }
    }
  }, [gameId]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  // Background refresh once connectivity is back after an offline load.
  useOnReconnect(() => {
    if (offline) void load();
  });

  const rename = useCallback(
    async (name: string) => {
      if (!gameId) return;

      const trimmed = name.trim();
      await renameGame(gameId, trimmed);

      if (!mounted.current) return;
      const next = game
        ? { ...game, name: trimmed, shortName: shortNameFor(trimmed) }
        : game;

      setGame(next);
      if (next) void cacheGame(next);
    },
    [game, gameId],
  );

  const missingId = !gameId;

  return {
    game,
    state: missingId ? 'error' : state,
    error: missingId
      ? t('missingGameId')
      : failure
        ? describeError(failure, language)
        : null,
    reload: load,
    rename,
    offline,
    lastSync,
  };
}
