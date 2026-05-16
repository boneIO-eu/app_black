/**
 * Memoized board+expander capacity calculator.
 *
 * Wraps `getOutputStats` in a `useMemo` so the dropdown Add button doesn't
 * recompute on every render. Exposes both raw counts and derived "full" flags.
 */
import { useMemo } from 'react';

import { getOutputStats } from '../helpers/expanderBoards';
import type { OutputEntity } from '../types/output';

export interface UseOutputCapacityReturn {
  boardCapacity: number;
  boardUsed: number;
  boardFull: boolean;
  expanderCapacity: number;
  expanderUsed: number;
  expanderFull: boolean;
  hasExpander: boolean;
  allFull: boolean;
}

export function useOutputCapacity(
  outputs: OutputEntity[],
  deviceType: string | undefined,
): UseOutputCapacityReturn {
  return useMemo(() => {
    const stats = getOutputStats(outputs, deviceType);
    const boardFull = stats.boardUsed >= stats.boardCapacity;
    // expanderCapacity = 0 means no expander configured → treat as "not full"
    // so dropdown still works for board, but allFull stays false on expander axis.
    const expanderFull = stats.expanderCapacity > 0 && stats.expanderUsed >= stats.expanderCapacity;
    return {
      ...stats,
      boardFull,
      expanderFull,
      hasExpander: stats.expanderCapacity > 0,
      // Only "all full" when both axes are saturated. If no expander, board-full alone counts.
      allFull: stats.expanderCapacity === 0 ? boardFull : boardFull && expanderFull,
    };
  }, [outputs, deviceType]);
}
