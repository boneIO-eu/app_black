import React from 'react';

interface SettingsToggleItem {
  /** Unique key for this toggle item */
  key: string;
  /** Display label for the toggle */
  label: string;
  /** Optional description text shown below the label */
  description?: string;
  /** Whether the toggle is checked */
  checked: boolean;
  /** Callback when the toggle value changes */
  onChange: (checked: boolean) => void;
  /** Whether the toggle is disabled */
  disabled?: boolean;
}

interface SettingsToggleGroupProps {
  /** List of toggle items to display */
  items: SettingsToggleItem[];
  /** Additional className for the outer container */
  className?: string;
}

/**
 * A compact, HA/iOS-style settings toggle group.
 * Renders multiple toggle items in a single bordered card with dividers.
 *
 * Each row has: label + description on the left, toggle on the right.
 *
 * @example
 * <SettingsToggleGroup items={[
 *   { key: 'show_in_ha', label: 'Show in HA', description: 'Hint text', checked: true, onChange: setShowInHa },
 *   { key: 'inverted', label: 'Inverted', checked: false, onChange: setInverted },
 * ]} />
 */
const SettingsToggleGroup: React.FC<SettingsToggleGroupProps> = ({ items, className = '' }) => {
  if (items.length === 0) return null;

  return (
    <div
      className={`rounded-[var(--radius-field)] border border-base-300 divide-y divide-base-200 bg-base-100 ${className}`}
    >
      {items.map((item) => (
        <label
          key={item.key}
          className={`flex items-center justify-between gap-4 px-4 py-3 ${
            item.disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
          }`}
        >
          <div className="min-w-0">
            <div className="text-sm font-medium">{item.label}</div>
            {item.description && (
              <div className="text-xs text-base-content/50 mt-0.5">{item.description}</div>
            )}
          </div>
          <input
            type="checkbox"
            className="toggle toggle-primary shrink-0"
            checked={item.checked}
            onChange={(e) => item.onChange(e.target.checked)}
            disabled={item.disabled}
          />
        </label>
      ))}
    </div>
  );
};

export default SettingsToggleGroup;
