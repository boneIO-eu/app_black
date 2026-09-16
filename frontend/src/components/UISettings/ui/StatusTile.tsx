import React from 'react';
import { cn } from '@/lib/utils';

export interface StatusTileProps {
  /** Optional icon */
  icon?: React.ReactNode;
  /** Label/title of the status metric */
  label: React.ReactNode;
  /** Main value */
  value: React.ReactNode;
  /** Optional suffix (e.g. '.local', 'kB', 'V') */
  suffix?: React.ReactNode;
  /** Optional badge component or status indicator */
  badge?: React.ReactNode;
  /** Optional action button on the right */
  action?: React.ReactNode;
  /** Additional container classes */
  className?: string;
}

/**
 * A read-only device property, shown as a value rather than as a disabled
 * input. Sits on the recessed `.stg-inset` surface so it reads as "this is
 * the current state", distinct from the fields below it that change it.
 */
export const StatusTile: React.FC<StatusTileProps> = ({
  icon,
  label,
  value,
  suffix,
  badge,
  action,
  className = '',
}) => {
  return (
    <div
      className={cn(
        'stg-inset flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-3.5 sm:p-4',
        className,
      )}
    >
      <div className="flex items-center gap-3.5 min-w-0">
        {icon && (
          <div className="stg-chip w-10 h-10 rounded-xl flex items-center justify-center text-[17px] shrink-0">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <span className="text-[11px] font-semibold text-base-content/50 uppercase tracking-[0.08em] block">
            {label}
          </span>
          <div className="flex items-baseline gap-2 mt-1 flex-wrap">
            <span className="font-mono text-base sm:text-lg font-bold text-base-content truncate">
              {value}
            </span>
            {suffix && (
              <span className="text-xs font-mono text-base-content/45">{suffix}</span>
            )}
            {badge}
          </div>
        </div>
      </div>
      {action && <div className="flex items-center gap-2 shrink-0">{action}</div>}
    </div>
  );
};

export default StatusTile;
