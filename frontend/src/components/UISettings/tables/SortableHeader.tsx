import React from 'react';
import type { SortConfig } from '@/hooks/useTableSort';
import { useTranslation } from '../../../hooks/useTranslation';

interface SortableHeaderProps {
  /** Column key used to identify this column in sort config */
  column: string;
  /** Display label for the column header */
  children: React.ReactNode;
  /** Current sort configuration */
  sortConfig: SortConfig;
  /** Callback to toggle sorting on this column */
  onToggleSort: (column: string) => void;
  /** Additional className for the th element */
  className?: string;
}

/**
 * A table header cell that supports click-to-sort with visual indicators.
 * Cycles through: unsorted -> ascending -> descending -> unsorted.
 */
const SortableHeader: React.FC<SortableHeaderProps> = ({
  column,
  children,
  sortConfig,
  onToggleSort,
  className = '',
}) => {
  const { t } = useTranslation();
  const isActive = sortConfig.column === column && sortConfig.direction !== null;
  const direction = isActive ? sortConfig.direction : null;

  const ariaLabel = direction === 'asc'
    ? t('table_sort.sorted_asc')
    : direction === 'desc'
      ? t('table_sort.sorted_desc')
      : t('table_sort.click_to_sort');

  return (
    <th
      className={`cursor-pointer select-none hover:bg-base-200 transition-colors ${className}`}
      onClick={() => onToggleSort(column)}
      title={ariaLabel}
    >
      <div className="flex items-center gap-1">
        <span>{children}</span>
        <span className="inline-flex flex-col text-[10px] leading-none ml-0.5 opacity-60">
          <span className={direction === 'asc' ? 'text-primary opacity-100' : 'opacity-30'}>▲</span>
          <span className={direction === 'desc' ? 'text-primary opacity-100' : 'opacity-30'}>▼</span>
        </span>
      </div>
    </th>
  );
};

export default SortableHeader;

interface ResetSortButtonProps {
  /** Whether sorting is currently active */
  isSorted: boolean;
  /** Callback to reset sorting */
  onReset: () => void;
}

/**
 * A small button to reset table sorting. Only visible when sorting is active.
 */
export const ResetSortButton: React.FC<ResetSortButtonProps> = ({ isSorted, onReset }) => {
  const { t } = useTranslation();

  if (!isSorted) return null;

  return (
    <button
      onClick={onReset}
      className="btn btn-ghost btn-xs gap-1 text-base-content/60 hover:text-base-content"
      title={t('table_sort.reset')}
    >
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
      {t('table_sort.reset')}
    </button>
  );
};
