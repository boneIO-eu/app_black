/**
 * Recent events per entity, for the long-press card.
 *
 * The controller keeps no history of its own: over the WebSocket it sends
 * the current state of every entity on connect, then each change as it
 * happens. Filtering that one stream by entity is all this does — so an
 * entity's list starts with the state it was in when the panel connected
 * ("on since yesterday 20:45"), and grows from there while the page is open.
 * A reload starts it again from that snapshot.
 *
 * Templates and irrigation are not on the socket; their views poll and feed
 * the same buffers through `recordEntityEvent` when a polled value changes.
 *
 * Kept in memory on purpose. Persisting it would show an old list with a
 * silent gap for the time the page was closed, which reads as "nothing
 * happened" when the truth is "nobody was watching".
 */
import type { StateUpdate } from '@/hooks/useWebSocket';
import type { TemplatesData } from '@/components/templates/types';
import type { IrrigationController } from '@/types/irrigation';

/** One recorded change. `value` is the raw state; the card translates it. */
export interface HistoryEntry {
  /** When it happened, epoch milliseconds. */
  at: number;
  /** The state or event: ON, single, opening, RUNNING, … */
  value: string;
  /** Secondary detail already formatted for display: 42%, 1.3s, a zone name. */
  detail?: string;
}

/** Entries kept per entity, newest first. */
export const MAX_ENTRIES = 30;

const buffers = new Map<string, HistoryEntry[]>();
const listeners = new Set<() => void>();
const EMPTY: HistoryEntry[] = [];

/** Buffer key: kind and id, because an output and an input can share an id. */
export function historyKey(kind: string, id: string): string {
  return `${kind}:${id}`;
}

function notify(): void {
  listeners.forEach((l) => l());
}

/**
 * Add an entry unless it repeats the newest one.
 *
 * A resync after a reconnect sends every state again with its original
 * timestamp; `sameAsLast` decides what counts as a repeat for this kind.
 */
export function recordEntityEvent(
  key: string,
  entry: HistoryEntry,
  sameAsLast: (last: HistoryEntry, next: HistoryEntry) => boolean = sameValue,
): void {
  const list = buffers.get(key) ?? EMPTY;
  if (list.length > 0 && sameAsLast(list[0], entry)) return;
  // A new array each time, so a subscriber can compare by reference.
  buffers.set(key, [entry, ...list].slice(0, MAX_ENTRIES));
  notify();
}

/** The buffer for one entity, newest first. Stable until it changes. */
export function getEntityHistory(key: string): HistoryEntry[] {
  return buffers.get(key) ?? EMPTY;
}

export function subscribeEntityHistory(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Drop everything. For tests; the app has no reason to call it. */
export function resetEntityHistory(): void {
  buffers.clear();
  notify();
}

/** A state that has not changed — the output is still ON. */
function sameValue(last: HistoryEntry, next: HistoryEntry): boolean {
  return last.value === next.value && last.detail === next.detail;
}

/** The same event delivered twice — an input click repeats its value on purpose. */
function sameEvent(last: HistoryEntry, next: HistoryEntry): boolean {
  return last.at === next.at && last.value === next.value;
}

/** Controller timestamps are unix seconds and sometimes missing. */
function toMs(seconds: number | null | undefined): number {
  return seconds ? Math.round(seconds * 1000) : Date.now();
}

/**
 * Feed one WebSocket frame into the buffers.
 *
 * Sensors and Modbus values are left out: they change continuously and
 * already have a graph, which says more than a list of numbers.
 */
export function recordFromStateUpdate(message: StateUpdate): void {
  switch (message.event_type) {
    case 'output': {
      const s = message.state;
      recordEntityEvent(historyKey('output', message.entity_id), {
        at: toMs(s.timestamp),
        value: s.state,
        detail: s.brightness != null && s.state === 'ON'
          ? `${Math.round((s.brightness / 255) * 100)}%`
          : undefined,
      });
      break;
    }
    case 'group': {
      recordEntityEvent(historyKey('group', message.entity_id), {
        at: toMs(message.state.timestamp),
        value: message.state.state,
      });
      break;
    }
    case 'input': {
      const s = message.state;
      // An input that has not fired since boot is in the snapshot as
      // "Unknown" with no time. That is not an event, and with no timestamp
      // every resync would look like a new one.
      if (!s.timestamp || !s.state || s.state === 'Unknown') break;
      recordEntityEvent(
        historyKey('input', message.entity_id),
        {
          at: toMs(s.timestamp),
          value: s.state,
          detail: s.state === 'long' && message.duration != null
            ? `${message.duration.toFixed(1)}s`
            : undefined,
        },
        sameEvent,
      );
      break;
    }
    case 'cover': {
      // Only the moves and where they ended: a cover in motion reports its
      // position several times a second, and a list of those is noise.
      const s = message.state;
      const moving = s.current_operation === 'opening' || s.current_operation === 'closing';
      recordEntityEvent(
        historyKey('cover', s.id || message.entity_id),
        {
          at: toMs(s.timestamp),
          value: moving ? s.current_operation : s.state,
          detail: moving ? undefined : `${s.position ?? 0}%`,
        },
      );
      break;
    }
    default:
      break;
  }
}

/**
 * Feed one poll of `/api/templates`. The poll carries no timestamps, so an
 * entry is dated when the change was seen — within the three-second poll.
 */
export function recordTemplates(data: TemplatesData): void {
  const now = Date.now();
  for (const th of data.thermostats ?? []) {
    const value = th.mode === 'off' ? 'off' : th.action === 'heating' ? 'heating' : 'idle';
    recordEntityEvent(historyKey('thermostat', th.id), {
      at: now,
      value,
      detail: value === 'off' ? undefined : `${th.target_temperature}°C`,
    });
  }
  for (const al of data.alarms ?? []) {
    recordEntityEvent(historyKey('alarm', al.id), { at: now, value: al.state });
  }
  for (const g of data.gates ?? []) {
    recordEntityEvent(historyKey('gate', g.id), { at: now, value: g.state });
  }
}

/** Feed one poll of `/api/irrigation`: what runs, and which zone. */
export function recordIrrigation(controllers: IrrigationController[]): void {
  const now = Date.now();
  for (const c of controllers) {
    recordEntityEvent(historyKey('irrigation', c.id), {
      at: now,
      value: c.state,
      detail: c.state === 'IDLE' ? undefined : c.active_zone?.name,
    });
  }
}
