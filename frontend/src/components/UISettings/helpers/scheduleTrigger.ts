/**
 * A schedule's trigger, and the pure functions the table and the editor share.
 *
 * Split out of the components so it can be tested: they render, and this
 * project's vitest runs in node with no DOM.
 */

/** Sun anchors, grouped the way someone shopping for one thinks about them. */
export const SUN_EVENT_GROUPS: { label: string; events: string[] }[] = [
  { label: 'event_form.condition_sun_group_basic', events: ['sunrise', 'sunset', 'solar_noon', 'solar_midnight'] },
  {
    label: 'event_form.condition_sun_group_twilight',
    events: ['civil_dawn', 'civil_dusk', 'nautical_dawn', 'nautical_dusk', 'astronomical_dawn', 'astronomical_dusk'],
  },
  {
    label: 'event_form.condition_sun_group_photographic',
    events: [
      'golden_hour_morning_start', 'golden_hour_morning_end',
      'golden_hour_evening_start', 'golden_hour_evening_end',
      'blue_hour_morning_start', 'blue_hour_morning_end',
      'blue_hour_evening_start', 'blue_hour_evening_end',
    ],
  },
];

export const DAY_OPTIONS = ['daily', 'weekdays', 'weekend', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

/** One action, as the config carries it. Its fields depend on `action`. */
export type ActionEntry = Record<string, unknown>;

/** A schedule's trigger, as `boneio/schema/schema.yaml` defines it.
 *
 * Offsets are numbers (seconds) coming from the backend and strings ("-15min")
 * going back, which is why both are allowed here. */
export interface ScheduleTrigger {
  type?: string;
  event?: string;
  at?: string;
  offset?: string | number;
  jitter?: string | number;
  days?: string;
}

/** One schedule. The index signature covers `condition`/`conditions`, which
 * are passed straight through to the shared condition editor. */
export interface ScheduleEntry {
  id: string;
  name?: string;
  enabled?: boolean;
  trigger?: ScheduleTrigger;
  on_missed?: string;
  actions?: ActionEntry[];
  [key: string]: unknown;
}

/** What the running controller says about a schedule the config only describes. */
export interface ScheduleStatus {
  id: string;
  name: string;
  enabled: boolean;
  actions: number;
  next_fire: string | null;
  last_fire: string | null;
  last_error: string | null;
}

/** Offsets come back from the backend in seconds; minutes is what people type. */
export function offsetToMinutes(value: string | number | undefined): string {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value === 'number') return String(Math.round(value / 60));
  const match = String(value).trim().match(/^([-+]?\d*\.?\d+)\s*(\w*)$/);
  if (!match) return '';
  const amount = parseFloat(match[1]);
  const unit = (match[2] || 's').toLowerCase();
  const seconds = unit.startsWith('h') ? amount * 3600 : unit.startsWith('m') ? amount * 60 : amount;
  return String(Math.round(seconds / 60));
}

/** The inverse, for what the editor sends back. Zero is no offset at all. */
export function minutesToOffset(minutes: string): string | undefined {
  const trimmed = minutes.trim();
  if (trimmed === '' || trimmed === '-') return undefined;
  const value = parseInt(trimmed, 10);
  if (isNaN(value) || value === 0) return undefined;
  return `${value}min`;
}

/** Local HH:MM from an ISO timestamp, with the date when it is not today. */
export function formatFire(iso: string | null, now: Date = new Date()): string {
  if (!iso) return '—';
  const when = new Date(iso);
  if (isNaN(when.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  const clock = `${pad(when.getHours())}:${pad(when.getMinutes())}`;
  const sameDay =
    when.getFullYear() === now.getFullYear() &&
    when.getMonth() === now.getMonth() &&
    when.getDate() === now.getDate();
  return sameDay ? clock : `${pad(when.getDate())}.${pad(when.getMonth() + 1)} ${clock}`;
}

/**
 * Apply one change to a trigger, keeping it a shape the loader accepts.
 *
 * `at` and `event` belong to different trigger types; carrying one over when
 * the type changes produces a config the backend rejects on save.
 *
 * @param trigger The trigger to change. Not mutated.
 * @param field Which field to set.
 * @param value The new value; `undefined` removes the field.
 * @returns A new trigger.
 */
export function withTriggerField(
  trigger: ScheduleTrigger | undefined,
  field: keyof ScheduleTrigger,
  value: string | undefined,
): ScheduleTrigger {
  const next: ScheduleTrigger = { ...(trigger || {}), [field]: value };
  if (field === 'type') {
    if (value === 'sun') delete next.at;
    else delete next.event;
  }
  if (value === undefined) delete next[field];
  return next;
}

/**
 * One line describing when a schedule fires, for a table row.
 *
 * @param entry The schedule.
 * @param t Translator; the anchor names and day names are localised.
 */
export function triggerSummary(entry: ScheduleEntry, t: (key: string) => string): string {
  const trigger = entry.trigger || {};
  const days = t(`schedule.days_${trigger.days || 'daily'}`);
  const offset = offsetToMinutes(trigger.offset);
  const shift = offset && offset !== '0'
    ? ` ${Number(offset) > 0 ? '+' : '−'}${Math.abs(Number(offset))} min`
    : '';

  if ((trigger.type || 'sun') === 'time') {
    return `${trigger.at || '--:--'}${shift} · ${days}`;
  }
  const event = trigger.event ? t(`sun.anchor_${trigger.event}`) : '—';
  return `${event}${shift} · ${days}`;
}

/** The distinct action types a schedule runs, for a table row. */
export function actionTypes(entry: ScheduleEntry): string[] {
  return [...new Set((entry.actions || []).map((a) => String(a.action || '')).filter(Boolean))];
}
