import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';

import { useI18n } from '@/lib/i18n-context';
import { describeError, fetchGame, renameGame } from '@/lib/telemetry-api';
import { shortNameFor, type Game } from '@/types/telemetry';

import type { LoadState } from '@/hooks/use-games';

/** Loads a single game (with sessions) and exposes a rename action. */
export function useGame(gameId: string | undefined) {
  const { language, t } = useI18n();
  const [game, setGame] = useState<Game | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [failure, setFailure] = useState<unknown>(null);

  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    if (!gameId) return;

    try {
      const next = await fetchGame(gameId);
      if (!mounted.current) return;

      if (!next) {
        setGame(null);
        setFailure(null);
        setState('error');
        return;
      }

      setGame(next);
      setFailure(null);
      setState('ready');
    } catch (caught) {
      if (!mounted.current) return;
      setFailure(caught);
      setState('error');
    }
  }, [gameId]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );
  const rename = useCallback(
    async (name: string) => {
      if (!gameId) return;

      const trimmed = name.trim();
      await renameGame(gameId, trimmed);

      if (!mounted.current) return;
      setGame((current) =>
        current ? { ...current, name: trimmed, shortName: shortNameFor(trimmed) } : current,
      );
    },
    [gameId],
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
  };
}
