import React from 'react';
import { cn } from '@/lib/utils';
import HelpLabel from '../components/HelpLabel';

interface FormInputToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  help?: string;
  /** Optional description shown below the label (used in card variant). */
  description?: string;
  /** Visual variant: 'form' (default) for settings forms, 'card' for standalone card style. */
  variant?: 'form' | 'card';
  /** Toggle color class, e.g. 'toggle-primary', 'toggle-secondary'. Default: 'toggle-primary'. */
  toggleColor?: string;
  /** Toggle size class, e.g. 'toggle-sm'. Default: none (standard size). */
  toggleSize?: string;
}

/**
 * Reusable toggle/checkbox form control with label and optional help/description text.
 *
 * Variants:
 * - `form` (default): inline form-control style with HelpLabel below.
 * - `card`: card-style with rounded border, title + description, suitable for settings panels.
 */
export const FormInputToggle: React.FC<FormInputToggleProps> = ({
  label,
  checked,
  onChange,
  help,
  description,
  variant = 'form',
  toggleColor = 'toggle-primary',
  toggleSize,
}) => {
  if (variant === 'card') {
    return (
      <label className="flex items-center gap-3 cursor-pointer bg-base-200/30 border border-base-200 rounded-xl p-3">
        <input
          type="checkbox"
          className={cn('toggle', toggleSize, toggleColor)}
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-base-content/80">{label}</p>
          {description && (
            <p className="text-xs text-base-content/40">{description}</p>
          )}
        </div>
      </label>
    );
  }

  return (
    <div className="form-control flex flex-col">
      <label className="label cursor-pointer justify-start gap-3">
        <input
          type="checkbox"
          className={cn('toggle', toggleSize, toggleColor)}
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="label-text font-medium">{label}</span>
      </label>
      {help && <HelpLabel>{help}</HelpLabel>}
    </div>
  );
};
