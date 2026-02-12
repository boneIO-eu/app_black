import { useState, useCallback } from 'react';

export type SortDirection = 'asc' | 'desc' | null;

export interface SortConfig {
  column: string;
  direction: SortDirection;
}

const STORAGE_PREFIX = 'boneio_table_sort_';

/**
 * Hook for table column sorting with localStorage persistence.
 * Each table is identified by a unique tableId so sorting is remembered per table.
 *
 * @param tableId - Unique identifier for the table (used as localStorage key suffix)
 * @returns Sort state, toggle handler, reset handler, and a comparator function
 */
export function useTableSort(tableId: string) {
  const storageKey = `${STORAGE_PREFIX}${tableId}`;

  const [sortConfig, setSortConfig] = useState<SortConfig>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.column && (parsed.direction === 'asc' || parsed.direction === 'desc')) {
          return parsed;
        }
      }
    } catch {
      // ignore parse errors
    }
    return { column: '', direction: null };
  });

  /**
   * Toggle sorting for a column. Cycles: asc -> desc -> none.
   */
  const toggleSort = useCallback((column: string) => {
    setSortConfig(prev => {
      let next: SortConfig;
      if (prev.column !== column) {
        next = { column, direction: 'asc' };
      } else if (prev.direction === 'asc') {
        next = { column, direction: 'desc' };
      } else {
        next = { column: '', direction: null };
      }

      try {
        if (next.direction === null) {
          localStorage.removeItem(storageKey);
        } else {
          localStorage.setItem(storageKey, JSON.stringify(next));
        }
      } catch {
        // localStorage full or unavailable
      }
      return next;
    });
  }, [storageKey]);

  /**
   * Reset sorting to default (no sort).
   */
  const resetSort = useCallback(() => {
    setSortConfig({ column: '', direction: null });
    try {
      localStorage.removeItem(storageKey);
    } catch {
      // ignore
    }
  }, [storageKey]);

  /**
   * Sort an array of { item, originalIndex } objects by a value accessor map.
   * The accessors map column names to functions that extract a comparable value from an item.
   */
  const sortItems = useCallback(<T,>(
    items: { item: T; originalIndex: number }[],
    accessors: Record<string, (item: T) => string | number | boolean | undefined | null>
  ): { item: T; originalIndex: number }[] => {
    if (!sortConfig.direction || !sortConfig.column) return items;

    const accessor = accessors[sortConfig.column];
    if (!accessor) return items;

    const sorted = [...items].sort((a, b) => {
      const valA = accessor(a.item);
      const valB = accessor(b.item);

      // Handle nullish values - push them to the end
      if (valA == null && valB == null) return 0;
      if (valA == null) return 1;
      if (valB == null) return -1;

      let comparison = 0;
      if (typeof valA === 'string' && typeof valB === 'string') {
        comparison = valA.localeCompare(valB, undefined, { sensitivity: 'base', numeric: true });
      } else if (typeof valA === 'boolean' && typeof valB === 'boolean') {
        comparison = (valA === valB) ? 0 : valA ? -1 : 1;
      } else {
        comparison = Number(valA) - Number(valB);
      }

      return sortConfig.direction === 'desc' ? -comparison : comparison;
    });

    return sorted;
  }, [sortConfig]);

  const isSorted = sortConfig.direction !== null;

  return { sortConfig, toggleSort, resetSort, sortItems, isSorted };
}
