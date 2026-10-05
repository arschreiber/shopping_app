/** ISO-Wochen-Arithmetik. Der Planer rechnet in Wochen, die UI zeigt Datumsspannen. */

export const DAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
export const DAY_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

export function isoWeekOf(date: Date): string {
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNumber = target.getUTCDay() || 7;
  target.setUTCDate(target.getUTCDate() + 4 - dayNumber);
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((target.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
  return `${target.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

export function currentIsoWeek(): string {
  return isoWeekOf(new Date());
}

export function parseIso(iso: string): { year: number; week: number } {
  const [year, week] = iso.toUpperCase().split("-W");
  return { year: Number(year), week: Number(week) };
}

export function mondayOf(iso: string): Date {
  const { year, week } = parseIso(iso);
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const dayNumber = jan4.getUTCDay() || 7;
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - dayNumber + 1 + (week - 1) * 7);
  return monday;
}

export function shiftIsoWeek(iso: string, delta: number): string {
  const monday = mondayOf(iso);
  monday.setUTCDate(monday.getUTCDate() + delta * 7);
  return isoWeekOf(new Date(monday.getUTCFullYear(), monday.getUTCMonth(), monday.getUTCDate()));
}

const MONTHS = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."];

export function formatRange(iso: string): string {
  const monday = mondayOf(iso);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  const sameMonth = monday.getUTCMonth() === sunday.getUTCMonth();
  const left = sameMonth
    ? `${monday.getUTCDate()}.`
    : `${monday.getUTCDate()}. ${MONTHS[monday.getUTCMonth()]}`;
  return `${left} – ${sunday.getUTCDate()}. ${MONTHS[sunday.getUTCMonth()]} ${sunday.getUTCFullYear()}`;
}

export function dateOfDay(iso: string, day: number): Date {
  const monday = mondayOf(iso);
  const target = new Date(monday);
  target.setUTCDate(monday.getUTCDate() + day);
  return target;
}

export function formatDay(iso: string, day: number): string {
  const date = dateOfDay(iso, day);
  return `${date.getUTCDate()}.${date.getUTCMonth() + 1}.`;
}

export function isToday(iso: string, day: number): boolean {
  const date = dateOfDay(iso, day);
  const now = new Date();
  return (
    date.getUTCFullYear() === now.getFullYear() &&
    date.getUTCMonth() === now.getMonth() &&
    date.getUTCDate() === now.getDate()
  );
}

/** Heute als YYYY-MM-DD in Ortszeit - `toISOString` wäre bis 2 Uhr nachts noch gestern. */
export function todayIsoDate(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Ist der Tag (YYYY-MM-DD) schon da? Heute zählt mit. */
export function hasArrived(isoDate: string, now: Date = new Date()): boolean {
  return isoDate <= todayIsoDate(now);
}
