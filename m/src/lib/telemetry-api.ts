import { DEFAULT_LANGUAGE, translate, type Language } from '@/lib/i18n';
import { supabase } from '@/lib/supabase';
import {
  downsampleSamples,
  mapGame,
  mapSample,
  type FpsSample,
  type Game,
  type GameRow,
  type SampleRow,
} from '@/types/telemetry';

/** Columns needed by the list and the detail screen (samples are loaded lazily). */
const GAME_SELECT =
  'id, name, process_name, created_at, sessions(id, played_at, avg_fps, min_fps, max_fps, duration_seconds)';

/** PresentMon sessions can have thousands of samples; the chart never needs more. */
const MAX_CHART_POINTS = 240;

/** PostgREST returns at most 1 000 rows per request unless configured higher. */
const SAMPLE_PAGE_SIZE = 1000;

const SAMPLE_PAGE_LIMIT = 50;

export function describeError(error: unknown, language: Language = DEFAULT_LANGUAGE): string {
  const message = error instanceof Error ? error.message : String(error ?? '');
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String((error as { code?: unknown }).code)
      : '';

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
  const { data, error } = await supabase.from('games').select(GAME_SELECT);

  if (error) throw error;

  return sortByRecent(((data ?? []) as GameRow[]).map(mapGame));
}

/** A single game with its sessions, or `null` when it no longer exists. */
export async function fetchGame(gameId: string): Promise<Game | null> {
  const { data, error } = await supabase
    .from('games')
    .select(GAME_SELECT)
    .eq('id', gameId)
    .maybeSingle();

  if (error) throw error;
  if (!data) return null;

  return mapGame(data as GameRow);
}

export type CreateGameInput = {
  name: string;
  processName?: string | null;
};

export async function createGame({ name, processName }: CreateGameInput): Promise<Game> {
  const trimmedName = name.trim();
  const trimmedProcess = processName?.trim() ?? '';

  const { data, error } = await supabase
    .from('games')
    .insert({
      name: trimmedName,
      process_name: trimmedProcess.length > 0 ? trimmedProcess : null,
    })
    .select('id, name, process_name, created_at')
    .single();

  if (error) throw error;

  return mapGame(data as GameRow);
}

export async function renameGame(gameId: string, name: string): Promise<void> {
  const { error } = await supabase
    .from('games')
    .update({ name: name.trim() })
    .eq('id', gameId);

  if (error) throw error;
}

/**
 * Loads every FPS sample of a session (paged) and averages them down to a
 * chart-friendly number of points.
 */
export async function fetchSessionSamples(sessionId: string): Promise<FpsSample[]> {
  const rows: SampleRow[] = [];
  let from = 0;

  for (let page = 0; page < SAMPLE_PAGE_LIMIT; page += 1) {
    const { data, error } = await supabase
      .from('fps_samples')
      .select('timestamp_offset, fps')
      .eq('session_id', sessionId)
      .order('timestamp_offset', { ascending: true })
      .order('id', { ascending: true })
      .range(from, from + SAMPLE_PAGE_SIZE - 1);

    if (error) throw error;

    const batch = (data ?? []) as SampleRow[];
    rows.push(...batch);

    if (batch.length < SAMPLE_PAGE_SIZE) break;
    from += SAMPLE_PAGE_SIZE;
  }

  return downsampleSamples(rows.map(mapSample), MAX_CHART_POINTS);
}
