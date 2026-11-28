/** The data model that the UI works with. Corresponds to the Supabase tables. */

export type FpsSample = {
  /** Seconds from the start of the session. */
  offsetSeconds: number;
  fps: number;
  /** Average GPU temperature in °C at the sample (`null` when not recorded). */
  gpuTemp?: number | null;
  /** Average CPU temperature in °C at the sample (`null` when not recorded). */
  cpuTemp?: number | null;
  /** GPU load in % at the sample (`null` when not recorded). */
  gpuLoad?: number | null;
  /** CPU load in % at the sample (`null` when not recorded). */
  cpuLoad?: number | null;
};

/**
 * Key graphics settings read from the game configuration (PC agent v1.2.0).
 * Present when the agent found them in the game's ini/cfg/json files.
 */
export type GameSettings = {
  quality?: string | null;
  dlss?: boolean | null;
  fsr?: boolean | null;
  ray_tracing?: boolean | null;
  vsync?: boolean | null;
  fps_limit?: number | null;
} & Record<string, unknown>;

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
  /** Game window resolution, e.g. `2560x1440` (`null` when unknown). */
  resolution?: string | null;
  /** `Fullscreen` / `Borderless` / `Windowed` (`null` when unknown). */
  displayMode?: string | null;
  /** `DX12` / `DX11` / `Vulkan` / `OpenGL` (`null` when unknown). */
  graphicsApi?: string | null;
  /** Key graphics settings from the game config (`null` when unknown). */
  gameSettings?: GameSettings | null;
  /** Free-form note typed by the user (`null` when empty). */
  note?: string | null;
  /** Average GPU temperature in °C during the session (`null` when unknown). */
  gpuTempAvg?: number | null;
  /** Maximum GPU temperature in °C during the session (`null` when unknown). */
  gpuTempMax?: number | null;
  /** Average GPU load in % during the session (`null` when unknown). */
  gpuLoadAvg?: number | null;
  /** Average CPU temperature in °C during the session (`null` when unknown). */
  cpuTempAvg?: number | null;
  cpuTempMax?: number | null;
  /** Average CPU load in % during the session (`null` when unknown). */
  cpuLoadAvg?: number | null;
};

export type Game = {
  id: string;
  name: string;
  processName: string | null;
  createdAt: string;
  /** Two-letter badge derived from the name. */
  shortName: string;
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
  resolution?: string | null;
  display_mode?: string | null;
  graphics_api?: string | null;
  game_settings?: Record<string, unknown> | null;
  note?: string | null;
  gpu_temp_avg?: number | string | null;
  gpu_temp_max?: number | string | null;
  gpu_load_avg?: number | string | null;
  cpu_temp_avg?: number | string | null;
  cpu_temp_max?: number | string | null;
  cpu_load_avg?: number | string | null;
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
  gpu_temp?: number | string | null;
  cpu_temp?: number | string | null;
  gpu_load?: number | string | null;
  cpu_load?: number | string | null;
};

/* -------------------------------------------------------------------------- */
/*  Mapping                                                                   */
/* -------------------------------------------------------------------------- */

const ACCENTS = ['#9BC7B2', '#DDA45E', '#C98A7D', '#8FA5C8', '#A9A0C9', '#B8C48F'] as const;

/** Darker equivalents keep the badge readable on white cards. */
const LIGHT_ACCENTS = ['#3F7F68', '#9A6B2F', '#9A5A4C', '#4F6A94', '#6B6396', '#6D7A42'] as const;

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

export function accentFor(id: string, mode: 'dark' | 'light' = 'dark'): string {
  const accents = mode === 'light' ? LIGHT_ACCENTS : ACCENTS;
  return accents[hashSeed(id) % accents.length];
}

export function shortNameFor(name: string): string {
  // Avoid `\p{…}` (not available in every Hermes build); this range covers
  // ASCII plus the Czech diacritics.
  const letters = name.replace(/[^0-9A-Za-zÀ-ž]/g, '');
  return letters.slice(0, 2).toUpperCase() || 'PC';
}

function toNullableNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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
    resolution: row.resolution ?? null,
    displayMode: row.display_mode ?? null,
    graphicsApi: row.graphics_api ?? null,
    gameSettings: row.game_settings ? (row.game_settings as GameSettings) : null,
    note: row.note ?? null,
    gpuTempAvg: toNullableNumber(row.gpu_temp_avg),
    gpuTempMax: toNullableNumber(row.gpu_temp_max),
    gpuLoadAvg: toNullableNumber(row.gpu_load_avg),
    cpuTempAvg: toNullableNumber(row.cpu_temp_avg),
    cpuTempMax: toNullableNumber(row.cpu_temp_max),
    cpuLoadAvg: toNullableNumber(row.cpu_load_avg),
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
    sessions,
  };
}

export function mapSample(row: SampleRow): FpsSample {
  return {
    offsetSeconds: Math.max(0, toNumber(row.timestamp_offset)),
    fps: toNumber(row.fps),
    gpuTemp: toNullableNumber(row.gpu_temp),
    cpuTemp: toNullableNumber(row.cpu_temp),
    gpuLoad: toNullableNumber(row.gpu_load),
    cpuLoad: toNullableNumber(row.cpu_load),
  };
}

function averageMetric(samples: FpsSample[], key: 'gpuTemp' | 'cpuTemp' | 'gpuLoad' | 'cpuLoad'): number | null {
  let sum = 0;
  let count = 0;
  for (const sample of samples) {
    const value = sample[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      sum += value;
      count += 1;
    }
  }
  return count > 0 ? Math.round((sum / count) * 10) / 10 : null;
}

/**
 * Point reduction for `react-native-gifted-charts`: keeps the **minimum** FPS
 * per bucket so drops are not smoothed away when the session has many samples
 * (PresentMon can produce thousands). `offsetSeconds` and hardware telemetry
 * fields keep their bucket averages.
 */
export function downsampleSamples(samples: FpsSample[], maxPoints: number): FpsSample[] {
  if (samples.length <= maxPoints) return samples;

  const bucketSize = Math.ceil(samples.length / maxPoints);
  const reduced: FpsSample[] = [];

  for (let start = 0; start < samples.length; start += bucketSize) {
    const bucket = samples.slice(start, start + bucketSize);
    const offsetSeconds =
      bucket.reduce((total, sample) => total + sample.offsetSeconds, 0) / bucket.length;
    const fps = Math.min(...bucket.map((sample) => sample.fps));

    reduced.push({
      offsetSeconds: Math.round(offsetSeconds),
      fps: Math.round(fps * 10) / 10,
      gpuTemp: averageMetric(bucket, 'gpuTemp'),
      cpuTemp: averageMetric(bucket, 'cpuTemp'),
      gpuLoad: averageMetric(bucket, 'gpuLoad'),
      cpuLoad: averageMetric(bucket, 'cpuLoad'),
    });
  }

  return reduced;
}

export function durationMinutes(session: GameSession): number {
  return Math.max(1, Math.round(session.durationSeconds / 60));
}
