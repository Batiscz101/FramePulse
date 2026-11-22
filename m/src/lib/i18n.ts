/**
 * Tiny hand-rolled translation layer – two languages, no runtime dependency.
 * `en` is the source of truth for the key set; `cs` must mirror it exactly.
 */

export const LANGUAGES = ['en', 'cs'] as const;

export type Language = (typeof LANGUAGES)[number];

export const DEFAULT_LANGUAGE: Language = 'en';

const en = {
  /* Shared actions */
  retry: 'Try again',
  cancel: 'Cancel',
  close: 'Close',
  save: 'Save',
  back: 'Back',
  backToList: 'Back to list',
  addGame: 'Add game',
  addGameSubmit: 'Add',
  renameGame: 'Rename game',
  languageToggle: 'Switch language',
  themeToggle: 'Switch theme',
  themeDark: 'Dark',
  themeLight: 'Light',
  offlineBadge: 'Offline data',
  offlineSynced: 'synced {time}',
  offlineHint: 'Showing data saved on this device.',

  /* Game list */
  gamesTitle: 'Your games',
  pcTelemetry: 'PC telemetry',
  searchGames: 'Search games',
  clearSearch: 'Clear search',
  recentlyPlayed: 'Recently played',
  loadingTelemetry: 'Loading telemetry…',
  loadFailed: "Couldn't load data",
  noGamesTitle: 'No games yet',
  noGamesBody: 'Start the pc-agent or add a game manually.',
  nothingFoundTitle: 'Nothing found',
  nothingFoundBody: 'Try a different game name.',

  /* Game card */
  cardAverageA11y: '{name}, average {fps} FPS',
  cardNoDataA11y: '{name}, no data yet',
  lastPlayed: 'last played {date}',
  noDataYet: 'no data yet',

  /* Game detail */
  loadingGame: 'Loading game…',
  gameNotFound: 'Game not found',
  gameNotFoundBody: 'This record may no longer be available.',
  missingGameId: 'The game identifier is missing.',
  manualGame: 'Manually added game',
  noDataTitle: 'No data yet',
  noDataBody:
    'Once the pc-agent uploads its first session, average FPS and the chart will appear here.',
  playDays: 'Days played',
  averageFps: 'Average FPS',
  minLabel: 'Min',
  maxLabel: 'Max',
  previousSession: 'vs. previous session',
  loadingChart: 'Loading FPS history…',
  chartLoadFailed: "Couldn't load FPS history",
  noSamplesTitle: 'No FPS samples',
  noSamplesBody: 'No chart data is stored for this session.',
  chartFootnote:
    'Data captured by PresentMon. The chart shows average FPS over short intervals of the session.',
  chartTitle: 'FPS over time',
  chartHint: 'Drag to inspect',

  /* Game form */
  addGameHint: 'The name appears in the app; the process lets the pc-agent recognize the game.',
  renameGameHint: 'The change is saved to Supabase and appears on your other devices.',
  gameName: 'Game name',
  gameNamePlaceholder: 'e.g. Cyberpunk 2077',
  processOptional: 'Process (optional)',
  processPlaceholder: 'e.g. Cyberpunk2077.exe',
  processName: 'Process name',

  /* Errors */
  errorSchemaMissing: 'Supabase tables are missing. Run supabase_schema.sql in the SQL Editor.',
  errorPermission:
    'The database rejected the request. Check RLS policies and grants in supabase_schema.sql.',
  errorDuplicate: 'A game with this process name already exists.',
  errorGeneric: 'Something went wrong. Please try again.',
} as const;

export type TranslationKey = keyof typeof en;

const cs: Record<TranslationKey, string> = {
  retry: 'Zkusit znovu',
  cancel: 'Zrušit',
  close: 'Zavřít',
  save: 'Uložit',
  back: 'Zpět',
  backToList: 'Zpět na seznam',
  addGame: 'Přidat hru',
  addGameSubmit: 'Přidat',
  renameGame: 'Přejmenovat hru',
  languageToggle: 'Přepnout jazyk',
  themeToggle: 'Přepnout motiv',
  themeDark: 'Tmavý',
  themeLight: 'Světlý',
  offlineBadge: 'Offline data',
  offlineSynced: 'staženo {time}',
  offlineHint: 'Zobrazují se data uložená v tomto zařízení.',

  gamesTitle: 'Vaše hry',
  pcTelemetry: 'telemetrie z PC',
  searchGames: 'Hledat hru',
  clearSearch: 'Vymazat hledání',
  recentlyPlayed: 'Naposledy hráno',
  loadingTelemetry: 'Načítám telemetrii…',
  loadFailed: 'Data se nepodařilo načíst',
  noGamesTitle: 'Zatím žádné hry',
  noGamesBody: 'Spusťte pc-agent, nebo hru přidejte ručně.',
  nothingFoundTitle: 'Nic nenalezeno',
  nothingFoundBody: 'Zkuste jiný název hry.',

  cardAverageA11y: '{name}, průměrně {fps} FPS',
  cardNoDataA11y: '{name}, zatím žádná data',
  lastPlayed: 'naposledy {date}',
  noDataYet: 'zatím žádná data',

  loadingGame: 'Načítám hru…',
  gameNotFound: 'Hra nenalezena',
  gameNotFoundBody: 'Záznam už možná není dostupný.',
  missingGameId: 'Chybí identifikátor hry.',
  manualGame: 'Ručně přidaná hra',
  noDataTitle: 'Zatím žádná data',
  noDataBody:
    'Jakmile pc-agent nahraje první seanci, objeví se zde průměrné FPS i graf průběhu.',
  playDays: 'Dny hraní',
  averageFps: 'Průměrné FPS',
  minLabel: 'Min',
  maxLabel: 'Max',
  previousSession: 'oproti předchozí seanci',
  loadingChart: 'Načítám průběh FPS…',
  chartLoadFailed: 'Průběh FPS se nepodařilo načíst',
  noSamplesTitle: 'Žádné vzorky FPS',
  noSamplesBody: 'Pro tuto seanci nejsou uložená žádná data průběhu.',
  chartFootnote:
    'Data zachycená přes PresentMon. Graf zobrazuje průměr FPS v kratších úsecích seance.',
  chartTitle: 'Průběh FPS',
  chartHint: 'Přejeďte prstem',

  addGameHint: 'Název se zobrazí v aplikaci, proces slouží pc-agentovi k rozpoznání hry.',
  renameGameHint: 'Změna se uloží do Supabase a projeví se i na ostatních zařízeních.',
  gameName: 'Název hry',
  gameNamePlaceholder: 'Např. Cyberpunk 2077',
  processOptional: 'Proces (nepovinné)',
  processPlaceholder: 'Např. Cyberpunk2077.exe',
  processName: 'Název procesu',

  errorSchemaMissing: 'Tabulky v Supabase nejsou vytvořené. Spusťte supabase_schema.sql v SQL Editoru.',
  errorPermission:
    'Databáze odmítla požadavek. Zkontrolujte RLS politiky a grants v supabase_schema.sql.',
  errorDuplicate: 'Hra s tímto názvem procesu už existuje.',
  errorGeneric: 'Něco se pokazilo. Zkuste to prosím znovu.',
};

const dictionaries: Record<Language, Record<TranslationKey, string>> = { en, cs };

export function isLanguage(value: unknown): value is Language {
  return typeof value === 'string' && (LANGUAGES as readonly string[]).includes(value);
}

export type TranslationParams = Record<string, string | number>;

export function translate(
  language: Language,
  key: TranslationKey,
  params?: TranslationParams,
): string {
  const template = dictionaries[language][key];

  if (!params) return template;

  return template.replace(/\{(\w+)\}/g, (match, token: string) =>
    token in params ? String(params[token]) : match,
  );
}

/* -------------------------------------------------------------------------- */
/*  Plurals                                                                   */
/* -------------------------------------------------------------------------- */

/** `0 games` / `1 game` / `2 games` · `0 her` / `1 hra` / `2 hry` / `5 her` */
export function gamesCount(language: Language, count: number): string {
  if (language === 'cs') {
    if (count === 0) return '0 her';
    if (count === 1) return '1 hra';
    if (count < 5) return `${count} hry`;
    return `${count} her`;
  }

  return count === 1 ? '1 game' : `${count} games`;
}

/** `no data` / `1 session` / `3 sessions` · `žádná data` / `1 seance` / `3 seance` */
export function sessionsCount(language: Language, count: number): string {
  if (language === 'cs') {
    if (count === 0) return 'žádná data';
    if (count === 1) return '1 seance';
    if (count < 5) return `${count} seance`;
    return `${count} seancí`;
  }

  if (count === 0) return 'no data';
  return count === 1 ? '1 session' : `${count} sessions`;
}

/** `1 day` / `3 days` · `1 den` / `3 dny` / `5 dní` */
export function daysCount(language: Language, count: number): string {
  if (language === 'cs') {
    if (count === 1) return '1 den';
    if (count < 5) return `${count} dny`;
    return `${count} dní`;
  }

  return count === 1 ? '1 day' : `${count} days`;
}

/** `1 point` / `240 points` · `1 bod` / `240 bodů` */
export function pointsCount(language: Language, count: number): string {
  if (language === 'cs') {
    if (count === 1) return '1 bod';
    if (count < 5) return `${count} body`;
    return `${count} bodů`;
  }

  return count === 1 ? '1 point' : `${count} points`;
}
