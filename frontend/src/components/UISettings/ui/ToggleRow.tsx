import React from 'react';
import { cn } from '@/lib/utils';

export interface ToggleRowProps {
  /** Toggle state */
  checked: boolean;
  /** Change handler */
  onChange: (checked: boolean) => void;
  /** Primary label */
  label: React.ReactNode;
  /** Explanation under the label */
  description?: React.ReactNode;
  /** Optional icon chip on the left */
  icon?: React.ReactNode;
  disabled?: boolean;
  /** Shown instead of the toggle while a request is in flight */
  busy?: boolean;
  /** Switch colour. `warning` marks a setting that is experimental or risky. */
  tone?: 'primary' | 'warning';
  className?: string;
}

/**
 * A switch with its explanation, as one clickable row.
 *
 * The settings pages had three different shapes for this — a bare
 * `label.cursor-pointer`, a toggle floating to the right of a paragraph, a
 * checkbox in a grid cell. One row means the hit area, the spacing and the
 * disabled treatment are the same everywhere.
 */
export const ToggleRow: React.FC<ToggleRowProps> = ({
  checked,
  onChange,
  label,
  description,
  icon,
  disabled = false,
  busy = false,
  tone = 'primary',
  className = '',
}) => {
  return (
    <label
      className={cn(
        'stg-inset flex items-center gap-3.5 p-3.5 sm:p-4 select-none transition-colors',
        disabled || busy ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer hover:border-base-content/15',
        className,
      )}
    >
      {icon && (
        <div className="stg-chip-neutral w-9 h-9 rounded-lg flex items-center justify-center text-[15px] shrink-0">
          {icon}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <span className="block text-sm font-medium text-base-content">{label}</span>
        {description && (
          <span className="block text-xs text-base-content/55 mt-0.5 leading-relaxed">
            {description}
          </span>
        )}
      </div>
      {busy && <span className="loading loading-spinner loading-xs text-primary shrink-0" />}
      <input
        type="checkbox"
        className={cn(
          'toggle toggle-sm shrink-0',
          tone === 'warning' ? 'toggle-warning' : 'toggle-primary',
        )}
        checked={checked}
        disabled={disabled || busy}
        onChange={e => onChange(e.target.checked)}
      />
    </label>
  );
};

export default ToggleRow;
