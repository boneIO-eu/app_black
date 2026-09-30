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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

/** Radix Select can't hold an empty value, so "no area" needs a stand-in. */
const NO_AREA = '__no_area__';

export interface AreaOption {
  id: string;
  name: string;
}

export interface AreaExtraOption {
  /** Value stored when selected. */
  value: string;
  /** Display label for the option. */
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
  /** Extra options listed right after "Brak obszaru" (e.g. "same as output"). */
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
      <Select
        value={value || NO_AREA}
        onValueChange={(v) => onChange(v === NO_AREA ? undefined : v)}
        disabled={areas.length === 0 && extraOptions.length === 0}
      >
        <SelectTrigger className="w-full" size={compact ? 'sm' : 'default'}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NO_AREA}>
            {areas.length === 0 && extraOptions.length === 0
              ? t('modbus_wizard.no_areas_defined') || 'No areas defined'
              : t('outputs.no_area') || 'Brak obszaru'}
          </SelectItem>
          {extraOptions.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
          {areas.map((a) => (
            <SelectItem key={a.id} value={a.id}>
              {a.name || a.id}
            </SelectItem>
          ))}
          {/* An area removed from the list still shows what the item points at. */}
          {value && !areas.some((a) => a.id === value) && !extraOptions.some((o) => o.value === value) && (
            <SelectItem value={value}>{value}</SelectItem>
          )}
        </SelectContent>
      </Select>
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
