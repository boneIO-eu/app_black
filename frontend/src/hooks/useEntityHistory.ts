import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import {
  getEntityHistory,
  subscribeEntityHistory,
  type HistoryEntry,
} from '@/utils/entityHistory';

/**
 * Recent events of one entity, newest first, updating live.
 *
 * @param key - From `historyKey(kind, id)`; null while no card is open.
 */
export function useEntityHistory(key: string | null): HistoryEntry[] {
  const getSnapshot = useCallback(() => (key ? getEntityHistory(key) : getEntityHistory('')), [key]);
  return useSyncExternalStore(subscribeEntityHistory, getSnapshot);
}

/**
 * The current time, re-read every `intervalMs` while `active`.
 *
 * For "3 s ago" labels that should keep counting while the card is open,
 * without a timer running for every card that is not.
 */
export function useNow(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [active, intervalMs]);
  return now;
}
