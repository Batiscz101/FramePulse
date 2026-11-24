import AsyncStorage from '@react-native-async-storage/async-storage';

import type { GameRow, SampleRow } from '@/types/telemetry';

/**
 * PostgREST (Neon Data API) client for the `games`, `sessions`, `fps_samples`
 * and `live_status` tables.
 *
 * The `apikey` and `Authorization` headers are sent only when an API key is
 * configured – the Data API serves the public endpoint (the `anonymous`
 * role) without one.
 */

/** Default Data API endpoint, overridable via `EXPO_PUBLIC_NEON_URL`. */
export const NEON_DATA_API_URL =
  process.env.EXPO_PUBLIC_NEON_URL?.trim() ||
  'https://ep-dark-base-bhm8rvp5.apirest.c-10.eu-central-1.aws.neon.tech/neondb/rest/v1';

const CONNECTION_URL_KEY = 'framepulse.connection.url';
const CONNECTION_API_KEY_KEY = 'framepulse.connection.apiKey';

/** Connection settings saved on the Connection screen (the key stays optional). */
export type ConnectionSettings = { url: string; apiKey: string };

/** Loads the saved connection settings, falling back to the default URL. */
export async function readConnectionSettings(): Promise<ConnectionSettings> {
  const [savedUrl, savedKey] = await Promise.all([
    AsyncStorage.getItem(CONNECTION_URL_KEY),
    AsyncStorage.getItem(CONNECTION_API_KEY_KEY),
  ]);

  return {
    url: savedUrl?.trim() || NEON_DATA_API_URL,
    apiKey: savedKey?.trim() ?? '',
  };
}

/** Saves the connection settings (persisted on the device, best-effort). */
export async function saveConnectionSettings(settings: ConnectionSettings): Promise<void> {
  await Promise.all([
    AsyncStorage.setItem(CONNECTION_URL_KEY, settings.url.trim()),
    AsyncStorage.setItem(CONNECTION_API_KEY_KEY, settings.apiKey.trim()),
  ]);
}

type PostgrestErrorBody = { code?: string; message?: string };

async function request<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  options: { params?: Record<string, string>; body?: unknown } = {},
): Promise<T> {
  const { url, apiKey } = await readConnectionSettings();

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) {
    headers['apikey'] = apiKey;
    headers['Authorization'] = `Bearer ${apiKey}`;
  }

  const target = new URL(path, url);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    target.searchParams.set(key, value);
  }

  const response = await fetch(target.toString(), {
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  const payload = (await response.json().catch(() => null)) as PostgrestErrorBody | null;

  if (!response.ok) {
    const code = payload?.code ? `${payload.code}: ` : '';
    throw new Error(`${code}${payload?.message ?? `HTTP ${response.status}`}`);
  }

  return (payload ?? []) as T;
}

export async function listGames(select: string): Promise<GameRow[]> {
  return request<GameRow[]>('GET', '/games', { params: { select, order: 'name.asc' } });
}

export async function fetchGame(gameId: string, select: string): Promise<GameRow | null> {
  const rows = await request<GameRow[]>('GET', '/games', { params: { select, id: `eq.${gameId}` } });
  return rows[0] ?? null;
}

export async function insertGame(
  game: { name: string; process_name: string | null },
  select: string,
): Promise<GameRow> {
  const rows = await request<GameRow[]>('POST', '/games', {
    params: { select },
    body: { name: game.name, process_name: game.process_name || null },
  });
  return rows[0];
}

export async function updateGame(gameId: string, name: string): Promise<void> {
  await request('PATCH', '/games', { params: { id: `eq.${gameId}` }, body: { name } });
}

export async function updateSessionNote(sessionId: string, note: string | null): Promise<void> {
  await request('PATCH', '/sessions', {
    params: { id: `eq.${sessionId}` },
    body: { note: note && note.length > 0 ? note : null },
  });
}

/** PresentMon sessions can have thousands of samples; the chart never needs more. */
const SAMPLE_PAGE_SIZE = 1000;
const SAMPLE_PAGE_LIMIT = 50;

export async function fetchSessionSamples(sessionId: string): Promise<SampleRow[]> {
  const rows: SampleRow[] = [];

  for (let offset = 0; offset < SAMPLE_PAGE_LIMIT * SAMPLE_PAGE_SIZE; offset += SAMPLE_PAGE_SIZE) {
    const batch = await request<SampleRow[]>('GET', '/fps_samples', {
      params: {
        select: 'timestamp_offset, fps, gpu_temp, cpu_temp, gpu_load, cpu_load',
        session_id: `eq.${sessionId}`,
        order: 'timestamp_offset.asc, id.asc',
        offset: String(offset),
        limit: String(SAMPLE_PAGE_SIZE),
      },
    });
    rows.push(...batch);
    if (batch.length < SAMPLE_PAGE_SIZE) break;
  }

  return rows;
}

/** Row of the `live_status` table as written by the PC agent. */
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
  gpu_load?: number | string | null;
  cpu_load?: number | string | null;
  updated_at: string | null;
};

export async function fetchLiveStatus(): Promise<LiveStatusRow | null> {
  const rows = await request<LiveStatusRow[]>('GET', '/live_status', {
    params: { select: '*', id: 'eq.default' },
  });
  return rows[0] ?? null;
}
