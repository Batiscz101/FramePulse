import AsyncStorage from '@react-native-async-storage/async-storage';

import type { GameRow, SampleRow } from '@/types/telemetry';

/**
 * PostgREST (Neon Data API) client for the `games`, `sessions`, `fps_samples`
 * and `live_status` tables.
 *
 * When a static JWT (`eyJ...`) is provided in `apiKey`, it is sent directly as
 * the Bearer token. Otherwise an anonymous JWT is fetched from Neon Auth
 * (`<neon_auth_url>/token/anonymous`), cached in memory, and refreshed
 * automatically on expiry or HTTP 401 / PGRST302.
 */

/** Default Data API endpoint, overridable via `EXPO_PUBLIC_NEON_URL`. */
export const NEON_DATA_API_URL =
  process.env.EXPO_PUBLIC_NEON_URL?.trim() ||
  'https://ep-dark-base-bhm8rvp5.apirest.c-10.eu-central-1.aws.neon.tech/neondb/rest/v1';

/** Optional explicit Neon Auth base URL, overridable via `EXPO_PUBLIC_NEON_AUTH_URL`. */
export const NEON_AUTH_URL = process.env.EXPO_PUBLIC_NEON_AUTH_URL?.trim() || '';

const CONNECTION_URL_KEY = 'framepulse.connection.url';
const CONNECTION_API_KEY_KEY = 'framepulse.connection.apiKey';
const CONNECTION_AUTH_URL_KEY = 'framepulse.connection.authUrl';

const DEFAULT_ANON_TOKEN_TTL_MS = 10 * 60 * 1000;
const TOKEN_REFRESH_MARGIN_MS = 30 * 1000;

/** Connection settings saved on the Connection screen (the key stays optional). */
export type ConnectionSettings = { url: string; apiKey: string; authUrl?: string };

export class NeonApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = 'NeonApiError';
    this.status = status;
    this.code = code;
  }
}

export function isNeonAuthRequiredError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? '');
  const status =
    typeof error === 'object' && error !== null && 'status' in error
      ? Number((error as { status?: unknown }).status)
      : NaN;
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String((error as { code?: unknown }).code ?? '')
      : '';

  return (
    status === 401 ||
    code === 'PGRST302' ||
    /PGRST302|bearer token in jwt format/i.test(message)
  );
}

function isJwtToken(value: string): boolean {
  return value.trim().startsWith('eyJ');
}

/**
 * Derives the Neon Auth base URL from a Neon Data API URL unless an explicit
 * Auth URL is supplied (`*.apirest.*` -> `*.neonauth.*`, `/rest/v1` -> `/auth`).
 */
export function deriveNeonAuthUrl(dataApiUrl: string, explicitAuthUrl?: string): string {
  const explicit = explicitAuthUrl?.trim().replace(/\/+$/, '');
  if (explicit) return explicit;

  const raw = dataApiUrl.trim().replace(/\/+$/, '');
  if (!raw) return '';

  try {
    const parsed = new URL(raw);
    if (!parsed.hostname.includes('.apirest.')) return '';

    parsed.hostname = parsed.hostname.replace('.apirest.', '.neonauth.');
    const cleanPath = parsed.pathname.replace(/\/+$/, '');
    if (cleanPath.endsWith('/rest/v1')) {
      parsed.pathname = `${cleanPath.slice(0, -'/rest/v1'.length)}/auth`;
    } else if (!cleanPath.endsWith('/auth')) {
      parsed.pathname = cleanPath ? `${cleanPath}/auth` : '/auth';
    }
    parsed.search = '';
    parsed.hash = '';
    return parsed.toString().replace(/\/+$/, '');
  } catch {
    return '';
  }
}

type CachedToken = { authUrl: string; token: string; expiresAt: number };
let cachedToken: CachedToken | null = null;
let pendingTokenFetch: { authUrl: string; promise: Promise<string | null> } | null = null;

export function clearAnonymousTokenCache(): void {
  cachedToken = null;
  pendingTokenFetch = null;
}

function extractJwtFromPayload(payload: unknown, headers: Headers): string | null {
  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>;
    const nested =
      record.data && typeof record.data === 'object'
        ? (record.data as Record<string, unknown>)
        : null;
    for (const candidate of [
      record.token,
      record.access_token,
      nested?.token,
      nested?.access_token,
    ]) {
      if (typeof candidate === 'string' && candidate.trim()) {
        return candidate.trim();
      }
    }
  }

  const headerToken = headers.get('set-auth-jwt');
  return headerToken?.trim() || null;
}

function getJwtTtlMs(token: string): number {
  const parts = token.split('.');
  if (parts.length >= 2 && typeof atob === 'function') {
    try {
      const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
      const claims = JSON.parse(atob(padded)) as { exp?: unknown };
      if (typeof claims.exp === 'number' && Number.isFinite(claims.exp)) {
        const remainingMs = claims.exp * 1000 - Date.now() - TOKEN_REFRESH_MARGIN_MS;
        if (remainingMs > 0) {
          return Math.min(DEFAULT_ANON_TOKEN_TTL_MS, remainingMs);
        }
      }
    } catch {
      // Malformed or non-standard token payload – fall back to the default TTL.
    }
  }
  return DEFAULT_ANON_TOKEN_TTL_MS;
}

async function fetchAnonymousJwt(authUrl: string): Promise<string | null> {
  try {
    const response = await fetch(`${authUrl}/token/anonymous`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return null;

    const payload = (await response.json().catch(() => null)) as unknown;
    return extractJwtFromPayload(payload, response.headers);
  } catch {
    return null;
  }
}

async function getAnonymousJwt(authUrl: string, forceRefresh = false): Promise<string | null> {
  if (!authUrl) return null;

  if (forceRefresh) {
    if (cachedToken?.authUrl === authUrl) cachedToken = null;
    if (pendingTokenFetch?.authUrl === authUrl) pendingTokenFetch = null;
  } else if (cachedToken && cachedToken.authUrl === authUrl && Date.now() < cachedToken.expiresAt) {
    return cachedToken.token;
  }

  if (pendingTokenFetch && pendingTokenFetch.authUrl === authUrl) {
    return pendingTokenFetch.promise;
  }

  const promise = (async () => {
    const token = await fetchAnonymousJwt(authUrl);
    if (token) {
      cachedToken = {
        authUrl,
        token,
        expiresAt: Date.now() + getJwtTtlMs(token),
      };
    }
    return token;
  })().finally(() => {
    if (pendingTokenFetch?.promise === promise) {
      pendingTokenFetch = null;
    }
  });

  pendingTokenFetch = { authUrl, promise };
  return promise;
}

/** Loads the saved connection settings, falling back to the default URL. */
export async function readConnectionSettings(): Promise<ConnectionSettings> {
  const [savedUrl, savedKey, savedAuthUrl] = await Promise.all([
    AsyncStorage.getItem(CONNECTION_URL_KEY),
    AsyncStorage.getItem(CONNECTION_API_KEY_KEY),
    AsyncStorage.getItem(CONNECTION_AUTH_URL_KEY),
  ]);

  return {
    url: savedUrl?.trim() || NEON_DATA_API_URL,
    apiKey: savedKey?.trim() ?? '',
    authUrl: savedAuthUrl?.trim() || NEON_AUTH_URL,
  };
}

/** Saves the connection settings (persisted on the device, best-effort). */
export async function saveConnectionSettings(settings: ConnectionSettings): Promise<void> {
  clearAnonymousTokenCache();
  await Promise.all([
    AsyncStorage.setItem(CONNECTION_URL_KEY, settings.url.trim()),
    AsyncStorage.setItem(CONNECTION_API_KEY_KEY, settings.apiKey.trim()),
    AsyncStorage.setItem(CONNECTION_AUTH_URL_KEY, (settings.authUrl ?? '').trim()),
  ]);
}

type PostgrestErrorBody = { code?: string; message?: string };

async function request<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  options: { params?: Record<string, string>; body?: unknown } = {},
): Promise<T> {
  const { url, apiKey, authUrl: explicitAuthUrl } = await readConnectionSettings();

  const rawBase = url.trim().replace(/\/+$/, '');
  const normalizedBase = rawBase.endsWith('/rest/v1') ? rawBase : `${rawBase}/rest/v1`;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const target = new URL(`${normalizedBase}${normalizedPath}`);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    target.searchParams.set(key, value);
  }

  const trimmedKey = apiKey.trim();
  const hasStaticJwt = isJwtToken(trimmedKey);
  const resolvedAuthUrl = hasStaticJwt ? '' : deriveNeonAuthUrl(normalizedBase, explicitAuthUrl);
  const usesDynamicAuth = !hasStaticJwt && resolvedAuthUrl.length > 0;

  let authRetried = false;

  while (true) {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    };

    if (hasStaticJwt) {
      headers['apikey'] = trimmedKey;
      headers['Authorization'] = `Bearer ${trimmedKey}`;
    } else if (usesDynamicAuth) {
      const token = await getAnonymousJwt(resolvedAuthUrl);
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    } else if (trimmedKey) {
      headers['apikey'] = trimmedKey;
      headers['Authorization'] = `Bearer ${trimmedKey}`;
    }

    const response = await fetch(target.toString(), {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });

    const payload = (await response.json().catch(() => null)) as PostgrestErrorBody | null;

    if (
      !response.ok &&
      usesDynamicAuth &&
      !authRetried &&
      (response.status === 401 || payload?.code === 'PGRST302')
    ) {
      authRetried = true;
      const refreshed = await getAnonymousJwt(resolvedAuthUrl, true);
      if (refreshed) continue;
    }

    if (!response.ok) {
      const codePrefix = payload?.code ? `${payload.code}: ` : '';
      throw new NeonApiError(
        `${codePrefix}${payload?.message ?? `HTTP ${response.status}`}`,
        response.status,
        payload?.code,
      );
    }

    return (payload ?? []) as T;
  }
}

/** Verifies the configured Neon Data API endpoint and auth setup. */
export async function testConnection(): Promise<void> {
  await request<GameRow[]>('GET', '/games', { params: { select: 'id', limit: '1' } });
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
