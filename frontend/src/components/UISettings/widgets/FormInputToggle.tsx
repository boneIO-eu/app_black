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
      <label className="stg-inset flex items-center gap-3 cursor-pointer p-3">
        <input
          type="checkbox"
          className={cn('toggle', toggleSize, toggleColor)}
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-base-content">{label}</p>
          {description && (
            <p className="text-xs text-base-content/55 mt-0.5 leading-relaxed">{description}</p>
          )}
        </div>
      </label>
    );
  }

  return (
    <div className="form-control flex flex-col">
      <label className="flex cursor-pointer items-center gap-3">
        <input
          type="checkbox"
          className={cn('toggle', toggleSize, toggleColor)}
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="text-[13px] font-medium text-base-content/85">{label}</span>
      </label>
      {help && <HelpLabel>{help}</HelpLabel>}
    </div>
  );
};
