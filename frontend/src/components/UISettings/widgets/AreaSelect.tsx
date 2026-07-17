/**
 * Reusable Area/Room select widget.
 *
 * Provides a dropdown with all configured areas and a "None" option
 * to deselect. Works with the Radix Select primitive and i18n translations.
 *
 * Usage:
 *   <AreaSelect
 *     value={data.area}
 *     onChange={(area) => updateField('area', area)}
 *     areas={allAreas}
 *   />
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';

export interface AreaOption {
  id: string;
  name: string;
}

export interface AreaExtraOption {
  /** Value stored when selected. */
  value: string;
  /** Display label for the button. */
  label: string;
}

interface AreaSelectProps {
  /** Current area ID, or undefined/null for "no area". */
  value: string | undefined | null;
  /** Called with area ID or undefined when selection changes or is cleared. */
  onChange: (areaId: string | undefined) => void;
  /** List of available areas. */
  areas: AreaOption[];
  /** Optional label override (defaults to i18n 'outputs.area'). */
  label?: string;
  /** Optional hint text below the select (defaults to i18n-based hint). */
  hint?: string;
  /** Hide the hint text entirely. */
  hideHint?: boolean;
  /** Hide the label entirely. */
  hideLabel?: boolean;
  /** Additional className for the outer wrapper. */
  className?: string;
  /** Use compact (small) styling. */
  compact?: boolean;
  /** Extra option buttons rendered alongside "Brak obszaru" (e.g. "same as output"). */
  extraOptions?: AreaExtraOption[];
}

const AreaSelect: React.FC<AreaSelectProps> = ({
  value,
  onChange,
  areas,
  label,
  hint,
  hideHint = false,
  hideLabel = false,
  className = '',
  compact = false,
  extraOptions = [],
}) => {
  const { t } = useTranslation();

  const displayLabel = label ?? t('outputs.area');
  const displayHint =
    hint ??
    (areas.length === 0 ? t('outputs.area_empty_hint') : t('outputs.area_hint'));

  return (
    <div className={`form-control ${className}`}>
      {!hideLabel && (
        <label className={`label ${compact ? 'py-1' : ''}`}>
          <span className={`label-text ${compact ? 'text-sm font-semibold' : 'font-medium'}`}>
            {displayLabel}
          </span>
        </label>
      )}
      <div className="grid grid-cols-2 gap-1.5 mt-0.5">
        {areas.length > 0 && (
          <button
            type="button"
            onClick={() => onChange(undefined)}
            className={`btn btn-sm font-medium transition-all truncate ${
              !value
                ? 'btn-primary'
                : 'btn-outline border-base-300 hover:border-base-400 bg-base-100 hover:bg-base-200/50 text-base-content/70'
            }`}
          >
            {t('outputs.no_area') || 'Brak obszaru'}
          </button>
        )}
        {extraOptions.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(value === opt.value ? undefined : opt.value)}
            className={`btn btn-sm font-medium transition-all truncate ${
              value === opt.value
                ? 'btn-primary'
                : 'btn-outline border-base-300 hover:border-base-400 bg-base-100 hover:bg-base-200/50 text-base-content/70'
            }`}
          >
            {opt.label}
          </button>
        ))}
        {areas.map((a) => {
          const isSelected = value === a.id;
          return (
            <button
              key={a.id}
              type="button"
              onClick={() => onChange(isSelected ? undefined : a.id)}
              className={`btn btn-sm font-medium transition-all truncate ${
                isSelected 
                  ? 'btn-primary' 
                  : 'btn-outline border-base-300 hover:border-base-400 bg-base-100 hover:bg-base-200/50'
              }`}
            >
              {a.name || a.id}
            </button>
          );
        })}
        {areas.length === 0 && (
          <span className="text-xs text-base-content/50 italic py-1 col-span-2">
            {t('modbus_wizard.no_areas_defined') || 'No areas defined'}
          </span>
        )}
      </div>
      {!hideHint && (
        <label className="label py-1">
          <span className="label-text-alt whitespace-normal break-words text-base-content/60">
            {displayHint}
          </span>
        </label>
      )}
    </div>
  );
};

export default AreaSelect;
