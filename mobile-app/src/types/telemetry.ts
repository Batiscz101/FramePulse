/** Datový model, se kterým pracuje UI. Odpovídá tabulkám v Supabase. */

export type FpsSample = {
  /** Seconds from the start of the session. */
  offsetSeconds: number;
  fps: number;
};

export type GameSession = {
  id: string;
  gameId: string;
  /** Local calendar date of the session, `YYYY-MM-DD`. */
  date: string;
  /** Local start of the session, `HH:MM`. */
  startedAt: string;
  /** Local minutes since midnight of the session start. */
  startMinutes: number;
  durationSeconds: number;
  avgFps: number;
  minFps: number;
  maxFps: number;
};

export type Game = {
  id: string;
  name: string;
  processName: string | null;
  createdAt: string;
  /** Two-letter badge derived from the name. */
  shortName: string;
  /** Muted accent colour derived from the id. */
  accent: string;
  /** Newest session first. */
  sessions: GameSession[];
};

/* -------------------------------------------------------------------------- */
/*  Rows as returned by PostgREST                                             */
/* -------------------------------------------------------------------------- */

export type SessionRow = {
  id: string;
  played_at: string;
  avg_fps: number | string | null;
  min_fps: number | string | null;
  max_fps: number | string | null;
  duration_seconds: number | string | null;
};

export type GameRow = {
  id: string;
  name: string;
  process_name: string | null;
  created_at: string;
  sessions?: SessionRow[] | null;
};

export type SampleRow = {
  timestamp_offset: number | string | null;
  fps: number | string | null;
};

/* -------------------------------------------------------------------------- */
/*  Mapping                                                                   */
/* -------------------------------------------------------------------------- */

const ACCENTS = ['#9BC7B2', '#DDA45E', '#C98A7D', '#8FA5C8', '#A9A0C9', '#B8C48F'] as const;

function hashSeed(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function toNumber(value: number | string | null | undefined): number {
  const parsed = typeof value === 'number' ? value : Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

/** Breaks an ISO timestamp into local date/time parts for the UI. */
export function localPlayParts(isoTimestamp: string): {
  date: string;
  startedAt: string;
  startMinutes: number;
} {
  const parsed = new Date(isoTimestamp);

  if (Number.isNaN(parsed.getTime())) {
    const fallbackDate = isoTimestamp.slice(0, 10);
    return { date: fallbackDate, startedAt: '00:00', startMinutes: 0 };
  }

  const hours = parsed.getHours();
  const minutes = parsed.getMinutes();

  return {
    date: `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`,
    startedAt: `${pad(hours)}:${pad(minutes)}`,
    startMinutes: hours * 60 + minutes,
  };
}

export function accentFor(id: string): string {
  return ACCENTS[hashSeed(id) % ACCENTS.length];
}

export function shortNameFor(name: string): string {
  // Avoid `\p{…}` (not available in every Hermes build); this range covers
  // ASCII plus the Czech diacritics.
  const letters = name.replace(/[^0-9A-Za-zÀ-ž]/g, '');
  return letters.slice(0, 2).toUpperCase() || 'PC';
}

export function mapSession(row: SessionRow, gameId: string): GameSession {
  const parts = localPlayParts(row.played_at);

  return {
    id: row.id,
    gameId,
    date: parts.date,
    startedAt: parts.startedAt,
    startMinutes: parts.startMinutes,
    durationSeconds: Math.max(0, toNumber(row.duration_seconds)),
    avgFps: toNumber(row.avg_fps),
    minFps: toNumber(row.min_fps),
    maxFps: toNumber(row.max_fps),
  };
}

export function mapGame(row: GameRow): Game {
  const sessions = (row.sessions ?? [])
    .map((session) => mapSession(session, row.id))
    .sort((left, right) => {
      // Newest session first (same-day sessions sorted by start time).
      if (left.date === right.date) return right.startMinutes - left.startMinutes;
      return right.date.localeCompare(left.date);
    });

  return {
    id: row.id,
    name: row.name,
    processName: row.process_name,
    createdAt: row.created_at,
    shortName: shortNameFor(row.name),
    accent: accentFor(row.id),
    sessions,
  };
}

export function mapSample(row: SampleRow): FpsSample {
  return {
    offsetSeconds: Math.max(0, toNumber(row.timestamp_offset)),
    fps: toNumber(row.fps),
  };
}

/**
 * Averaging buckets keeps `react-native-gifted-charts` responsive on long
 * sessions (PresentMon can produce thousands of samples per session).
 */
export function downsampleSamples(samples: FpsSample[], maxPoints: number): FpsSample[] {
  if (samples.length <= maxPoints) return samples;

  const bucketSize = Math.ceil(samples.length / maxPoints);
  const reduced: FpsSample[] = [];

  for (let start = 0; start < samples.length; start += bucketSize) {
    const bucket = samples.slice(start, start + bucketSize);
    const offsetSeconds =
      bucket.reduce((total, sample) => total + sample.offsetSeconds, 0) / bucket.length;
    const fps = bucket.reduce((total, sample) => total + sample.fps, 0) / bucket.length;

    reduced.push({
      offsetSeconds: Math.round(offsetSeconds),
      fps: Math.round(fps * 10) / 10,
    });
  }

  return reduced;
}

export function durationMinutes(session: GameSession): number {
  return Math.max(1, Math.round(session.durationSeconds / 60));
}
