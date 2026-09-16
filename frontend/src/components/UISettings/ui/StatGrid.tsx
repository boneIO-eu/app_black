import React from 'react';
import { cn } from '@/lib/utils';

export interface StatItem {
  /** Short caption above the value */
  label: React.ReactNode;
  /** The value itself — text, a badge, anything inline */
  value: React.ReactNode;
  /** Render the value in a monospace face (times, versions, addresses) */
  mono?: boolean;
  /** Optional hint under the value */
  hint?: React.ReactNode;
}

export interface StatGridProps {
  items: StatItem[];
  /** Columns at the `sm` breakpoint and up. Stacks on phones either way. */
  columns?: 2 | 3 | 4;
  className?: string;
}

/**
 * A strip of read-only facts at the top of a page — timezone and clock,
 * version and uptime, broker and port.
 *
 * Every page that needed one used to hand-roll a grid of `<span>`s with
 * slightly different label sizes and opacities; this is that grid, once.
 */
export const StatGrid: React.FC<StatGridProps> = ({ items, columns = 3, className = '' }) => {
  const cols = {
    2: 'sm:grid-cols-2',
    3: 'sm:grid-cols-3',
    4: 'sm:grid-cols-2 lg:grid-cols-4',
  }[columns];

  return (
    <div className={cn('stg-inset grid grid-cols-1 gap-px overflow-hidden', cols, className)}>
      {items.map((item, i) => (
        <div
          key={i}
          className={cn(
            'flex flex-col gap-1.5 p-3.5 sm:p-4',
            // A hairline between cells, drawn by the gap showing the border
            // colour through — cheaper than per-cell borders that double up.
            'bg-base-100/60',
          )}
        >
          <span className="text-[11px] font-semibold text-base-content/50 uppercase tracking-[0.08em]">
            {item.label}
          </span>
          <div
            className={cn(
              'text-sm font-semibold text-base-content leading-snug',
              item.mono && 'font-mono',
            )}
          >
            {item.value}
          </div>
          {item.hint && (
            <span className="text-xs text-base-content/50 leading-relaxed">{item.hint}</span>
          )}
        </div>
      ))}
    </div>
  );
};

export default StatGrid;
