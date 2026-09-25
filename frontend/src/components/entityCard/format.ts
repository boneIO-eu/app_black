/**
 * Words and times for the long-press card. Kept apart from the components so
 * both can use them without upsetting fast refresh.
 */
import type { HistoryEntry } from '@/utils/entityHistory';

type T = (key: string, params?: Record<string, string | number>) => string;

/** A translation, or the raw value when there is none for it. */
function tOr(t: T, key: string, fallback: string): string {
  const s = t(key);
  return s === key ? fallback : s;
}

/**
 * "3 s temu", "5 min temu", then the clock time once it is old enough that
 * a relative figure stops meaning anything.
 */
export function formatAgo(at: number, now: number, t: T): string {
  const s = Math.max(0, Math.round((now - at) / 1000));
  if (s < 5) return t('entity_card.just_now');
  if (s < 60) return t('entity_card.ago_s', { n: s });
  if (s < 3600) return t('entity_card.ago_min', { n: Math.floor(s / 60) });
  if (s < 86400) return t('entity_card.ago_h', { n: Math.floor(s / 3600) });
  return formatClock(at, now);
}

/** Clock time today, date and time before that. */
export function formatClock(at: number, now: number): string {
  const d = new Date(at);
  const sameDay = new Date(now).toDateString() === d.toDateString();
  return sameDay
    ? d.toLocaleTimeString()
    : d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/** ON / OFF in words. */
export function outputValueLabel(value: string, t: T): string {
  if (value === 'ON') return t('entity_card.state_on');
  if (value === 'OFF') return t('entity_card.state_off');
  return value;
}

/** single → "Pojedyncze", pressed → "Wciśnięty". */
export function inputValueLabel(value: string, t: T): string {
  return tOr(t, `binding_matrix.legend_${value}`, value);
}

/** opening → "otwieranie", open → "Otwarta". */
export function coverValueLabel(value: string, t: T): string {
  if (value === 'open') return t('entity_card.cover_open');
  if (value === 'closed') return t('entity_card.cover_closed');
  return tOr(t, `covers.${value}`, value);
}

/** Formatters for the event list, by kind. */
export const historyFormatters = {
  output: (t: T) => (e: HistoryEntry) => outputValueLabel(e.value, t),
  input: (t: T) => (e: HistoryEntry) => inputValueLabel(e.value, t),
  cover: (t: T) => (e: HistoryEntry) => coverValueLabel(e.value, t),
  thermostat: (t: T) => (e: HistoryEntry) => tOr(t, `templates.${e.value}`, e.value),
  alarm: (t: T) => (e: HistoryEntry) => tOr(t, `templates.${e.value}`, e.value),
  gate: (t: T) => (e: HistoryEntry) => tOr(t, `templates.gate_${e.value}`, e.value),
  irrigation: (t: T) => (e: HistoryEntry) => tOr(t, `irrigation.state_${e.value.toLowerCase()}`, e.value),
};
