import { DEFAULT_LANGUAGE, translate, type Language } from '@/lib/i18n';
import {
  fetchGame as fetchGameRow,
  fetchLiveStatus as fetchLiveStatusRow,
  fetchSessionSamples as fetchSampleRows,
  insertGame,
  isNeonAuthRequiredError,
  listGames,
  updateGame,
  updateSessionNote as updateSessionNoteRow,
  type LiveStatusRow,
} from '@/lib/supabase';
import {
  downsampleSamples,
  mapGame,
  mapSample,
  type FpsSample,
  type Game,
} from '@/types/telemetry';

/** Columns needed by the list and the detail screen (samples are loaded lazily). */
const GAME_SELECT =
  'id, name, process_name, created_at, sessions(id, played_at, avg_fps, min_fps, max_fps, duration_seconds, resolution, display_mode, graphics_api, game_settings, note, gpu_temp_avg, gpu_temp_max, gpu_load_avg, cpu_temp_avg, cpu_temp_max, cpu_load_avg)';

/** PresentMon sessions can have thousands of samples; the chart never needs more. */
const MAX_CHART_POINTS = 75;

export function describeError(error: unknown, language: Language = DEFAULT_LANGUAGE): string {
  const message = error instanceof Error ? error.message : String(error ?? '');
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String((error as { code?: unknown }).code)
      : '';

  if (isNeonAuthRequiredError(error)) {
    return translate(language, 'errorNeonAuth');
  }

  if (code === '42P01' || code === 'PGRST205' || /schema cache/i.test(message)) {
    return translate(language, 'errorSchemaMissing');
  }

  if (code === '42501' || /permission denied/i.test(message)) {
    return translate(language, 'errorPermission');
  }

  if (code === '23505' || /duplicate key/i.test(message)) {
    return translate(language, 'errorDuplicate');
  }

  return message || translate(language, 'errorGeneric');
}

function sortByRecent(games: Game[]): Game[] {
  return [...games].sort((left, right) => {
    const leftLatest = left.sessions[0];
    const rightLatest = right.sessions[0];

    if (leftLatest && rightLatest) {
      if (leftLatest.date !== rightLatest.date) {
        return rightLatest.date.localeCompare(leftLatest.date);
      }
      return rightLatest.startMinutes - leftLatest.startMinutes;
    }

    if (leftLatest) return -1;
    if (rightLatest) return 1;
    return left.name.localeCompare(right.name, 'cs-CZ');
  });
}

/** All games with their sessions, newest activity first. */
export async function fetchGames(): Promise<Game[]> {
  const rows = await listGames(GAME_SELECT);
  return sortByRecent(rows.map(mapGame));
}

/** A single game with its sessions, or `null` when it no longer exists. */
export async function fetchGame(gameId: string): Promise<Game | null> {
  const row = await fetchGameRow(gameId, GAME_SELECT);
  return row ? mapGame(row) : null;
}

export type CreateGameInput = {
  name: string;
  processName?: string | null;
};

export async function createGame({ name, processName }: CreateGameInput): Promise<Game> {
  const trimmedName = name.trim();
  const trimmedProcess = processName?.trim() ?? '';

  const row = await insertGame(
    { name: trimmedName, process_name: trimmedProcess.length > 0 ? trimmedProcess : null },
    'id, name, process_name, created_at',
  );

  return mapGame(row);
}

export async function renameGame(gameId: string, name: string): Promise<void> {
  await updateGame(gameId, name.trim());
}

/** Saves a user-written note on a session (null clears it). */
export async function updateSessionNote(sessionId: string, note: string | null): Promise<void> {
  await updateSessionNoteRow(sessionId, note);
}

/**
 * Loads every FPS sample of a session and reduces them down to a
 * chart-friendly number of points (minimum FPS per bucket when downsampled).
 */
export async function fetchSessionSamples(sessionId: string): Promise<FpsSample[]> {
  const rows = await fetchSampleRows(sessionId);
  const mapped = rows.map(mapSample).sort((left, right) => left.offsetSeconds - right.offsetSeconds);
  return downsampleSamples(mapped, MAX_CHART_POINTS);
}

export async function fetchLiveStatus(): Promise<LiveStatusRow | null> {
  return fetchLiveStatusRow();
}
