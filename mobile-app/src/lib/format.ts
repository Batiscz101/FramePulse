import type { Language } from '@/lib/i18n';

const EN_MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const EN_MONTHS_SHORT = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

const CS_MONTHS_GENITIVE = [
  'ledna',
  'února',
  'března',
  'dubna',
  'května',
  'června',
  'července',
  'srpna',
  'září',
  'října',
  'listopadu',
  'prosince',
];

const WEEKDAYS_SHORT: Record<Language, string[]> = {
  en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
  cs: ['Ne', 'Po', 'Út', 'St', 'Čt', 'Pá', 'So'],
};

type ParsedDate = { day: number; month: number; year: number; weekday: number };

/** Parses an ISO `YYYY-MM-DD` value without timezone drift. */
export function parseDate(isoDate: string): ParsedDate {
  const [year, month, day] = isoDate.split('-').map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return { day, month, year, weekday };
}

/** `2026-11-16` -> `16. 11.` (cs) / `Nov 16` (en) */
export function formatShortDate(isoDate: string, language: Language = 'en'): string {
  const { day, month } = parseDate(isoDate);
  if (language === 'cs') return `${day}. ${month}.`;
  return `${EN_MONTHS_SHORT[month - 1]} ${day}`;
}

/** `2026-11-16` -> `16. listopadu 2026` (cs) / `November 16, 2026` (en) */
export function formatLongDate(isoDate: string, language: Language = 'en'): string {
  const { day, month, year } = parseDate(isoDate);
  if (language === 'cs') return `${day}. ${CS_MONTHS_GENITIVE[month - 1]} ${year}`;
  return `${EN_MONTHS[month - 1]} ${day}, ${year}`;
}

/** `2026-11-16` -> `Po` (cs) / `Mon` (en) */
export function formatWeekday(isoDate: string, language: Language = 'en'): string {
  return WEEKDAYS_SHORT[language][parseDate(isoDate).weekday];
}

/** `19:42` + 84 -> `19:42 – 21:06` */
export function formatTimeRange(startedAt: string, durationMin: number): string {
  const [hours, minutes] = startedAt.split(':').map(Number);
  const start = hours * 60 + minutes;
  const end = start + durationMin;
  return `${toClock(start)} – ${toClock(end)}`;
}

/** Minutes since midnight -> `HH:MM` (wraps past midnight, rounds fractions). */
export function toClock(minutesSinceMidnight: number): string {
  const normalized = ((Math.round(minutesSinceMidnight) % 1440) + 1440) % 1440;
  const hours = Math.floor(normalized / 60);
  const minutes = normalized % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

/** Rounded FPS value with a locale-aware thousands separator (`1 240` / `1,240`). */
export function formatFps(value: number, language: Language = 'en'): string {
  const rounded = Math.round(value);
  const separator = language === 'cs' ? '\u00A0' : ',';
  return String(rounded).replace(/\B(?=(\d{3})+(?!\d))/g, separator);
}

export function formatSignedFps(delta: number, language: Language = 'en'): string {
  const rounded = Math.round(delta);
  if (rounded === 0) return language === 'cs' ? 'bez změny' : 'no change';
  const sign = rounded > 0 ? '+' : '−';
  return `${sign}${formatFps(Math.abs(rounded), language)} FPS`;
}
