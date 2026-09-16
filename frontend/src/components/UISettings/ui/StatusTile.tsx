import React from 'react';

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
 * Clean status tile for displaying read-only device properties.
 * Eliminates the anti-pattern of using disabled text inputs.
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
      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-base-200/50 border border-base-200/90 transition-all ${className}`}
    >
      <div className="flex items-center gap-3.5 min-w-0">
        {icon && (
          <div className="w-10 h-10 rounded-xl bg-base-100 text-primary border border-base-200/80 shadow-xs flex items-center justify-center text-lg shrink-0">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <span className="text-xs font-semibold text-base-content/60 uppercase tracking-wider block">
            {label}
          </span>
          <div className="flex items-baseline gap-2 mt-0.5 flex-wrap">
            <span className="font-mono text-base sm:text-lg font-bold text-base-content truncate">
              {value}
            </span>
            {suffix && (
              <span className="text-xs font-mono text-base-content/50">
                {suffix}
              </span>
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
