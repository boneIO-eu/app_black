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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useTranslation } from '@/hooks/useTranslation';

export interface AreaOption {
  id: string;
  name: string;
}

interface AreaSelectProps {
  /** Current area ID, or undefined/null for "no area". */
  value: string | undefined | null;
  /** Called with area ID or undefined when "None" is selected. */
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
}

const NONE_VALUE = '_none_';

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
        value={value || NONE_VALUE}
        onValueChange={(v) => onChange(v === NONE_VALUE ? undefined : v)}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder={t('outputs.no_area')} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE_VALUE}>{t('outputs.no_area')}</SelectItem>
          {areas.map((area) => (
            <SelectItem key={area.id} value={area.id}>
              {area.name || area.id}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {!hideHint && (
        <label className="label">
          <span className="label-text-alt whitespace-normal wrap-break-word">
            {displayHint}
          </span>
        </label>
      )}
    </div>
  );
};

export default AreaSelect;
