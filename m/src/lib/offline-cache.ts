import AsyncStorage from '@react-native-async-storage/async-storage';

import type { FpsSample, Game } from '@/types/telemetry';

/**
 * Small JSON cache for offline browsing. Every successful Supabase read is
 * written here with a timestamp, and the same data is served when the network
 * is unavailable (including after a full app restart).
 */
const PREFIX = 'framepulse.cache';
const GAMES_KEY = `${PREFIX}.games`;

function gameKey(gameId: string): string {
  return `${PREFIX}.game.${gameId}`;
}

function samplesKey(sessionId: string): string {
  return `${PREFIX}.samples.${sessionId}`;
}

export type CacheEntry<T> = {
  data: T;
  /** Epoch milliseconds of the successful sync that produced this entry. */
  savedAt: number;
};

async function readEntry<T>(key: string): Promise<CacheEntry<T> | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return null;

    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return null;

    const entry = parsed as Partial<CacheEntry<T>>;
    if (typeof entry.savedAt !== 'number' || entry.data === undefined) return null;

    return { data: entry.data, savedAt: entry.savedAt };
  } catch {
    // A corrupted entry must never break the screen – behave as a cache miss.
    return null;
  }
}

async function writeEntry<T>(key: string, data: T): Promise<number> {
  const savedAt = Date.now();

  try {
    await AsyncStorage.setItem(key, JSON.stringify({ data, savedAt }));
  } catch {
    // Caching is best-effort; the freshly fetched data is still displayed.
  }

  return savedAt;
}

export function readCachedGames(): Promise<CacheEntry<Game[]> | null> {
  return readEntry<Game[]>(GAMES_KEY);
}

export function cacheGames(games: Game[]): Promise<number> {
  return writeEntry(GAMES_KEY, games);
}

export function readCachedGame(gameId: string): Promise<CacheEntry<Game> | null> {
  return readEntry<Game>(gameKey(gameId));
}

export function cacheGame(game: Game): Promise<number> {
  return writeEntry(gameKey(game.id), game);
}

export function readCachedSamples(sessionId: string): Promise<CacheEntry<FpsSample[]> | null> {
  return readEntry<FpsSample[]>(samplesKey(sessionId));
}

export function cacheSamples(sessionId: string, samples: FpsSample[]): Promise<number> {
  return writeEntry(samplesKey(sessionId), samples);
}
