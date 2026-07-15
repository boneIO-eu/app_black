import React, { useMemo } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import SearchableEntityPicker from '../SearchableEntityPicker';
import type { EntityItem } from '../EntitySelectDropdown';
import type { OutputActionProps } from './types';
import { formatActionLabel } from './helpers';

/** Output actions supported by local light/switch outputs. */
const OUTPUT_ONLY_ACTIONS = ['TOGGLE', 'ON', 'OFF'];

/**
 * Output Action component - handles local boneIO outputs.
 * Uses SearchableEntityPicker for output selection with search, area grouping and recent items.
 */
const OutputAction: React.FC<OutputActionProps> = ({
  action,
  onUpdate,
  t,
  allOutputs,
  allOutputGroups,
  allAreas = [],
  actionOutputOptions: _actionOutputOptions,
  savedOutputs,
  savedOutputGroups,
  preferredArea,
}) => {
  // Wrapper for onUpdate that removes deprecated 'pin' field
  const handleUpdate = (field: string, value: any) => {
    if (action.pin) {
      onUpdate('pin', undefined);
    }
    onUpdate(field, value);
  };

  /**
   * Check if an output is saved (committed) by comparing with saved data.
   */
  const isOutputSaved = (outputId: string, isGroup: boolean): boolean => {
    if (isGroup) {
      if (!savedOutputGroups) return true;
      return savedOutputGroups.some((g: any) => g.id === outputId);
    }
    if (!savedOutputs) return true;
    return savedOutputs.some((o: any) => {
      const id = o.id || o.boneio_output;
      return id === outputId;
    });
  };

  /** Get short label for output type, using i18n translations. */
  const getOutputTypeBadge = (outputType?: string): string | undefined => {
    if (!outputType || outputType === 'none') return undefined;
    return t(`outputs.output_types.${outputType}`) || outputType;
  };

  /** Get badge CSS class based on output type. */
  const getOutputBadgeClass = (outputType?: string): string => {
    switch (outputType) {
      case 'light': return 'badge-warning';
      case 'switch': return 'badge-info';
      case 'valve': return 'badge-accent';
      case 'button': return 'badge-secondary';
      default: return 'badge-ghost';
    }
  };

  /** Convert outputs + groups into EntityItem[] for the dropdown. */
  const outputItems: EntityItem[] = useMemo(() => {
    const outputs = allOutputs
      .filter((output: any) =>
        output &&
        typeof output === 'object' &&
        output.output_type?.toLowerCase() !== 'cover' &&
        (output.id || output.boneio_output)
      )
      .map((output: any): EntityItem => {
        const id = output.id || output.boneio_output;
        const saved = isOutputSaved(id, false);
        const outputType = output.output_type;
        return {
          id,
          name: output.name || id,
          area: output.area,
          badge: getOutputTypeBadge(outputType),
          badgeClass: getOutputBadgeClass(outputType),
          disabled: !saved,
          disabledLabel: !saved ? t('common.unsaved') : undefined,
        };
      });

    const groups = allOutputGroups
      .filter((group: any) => group && typeof group === 'object' && group.id)
      .map((group: any): EntityItem => {
        const saved = isOutputSaved(group.id, true);
        return {
          id: group.id,
          name: group.name || group.id,
          area: group.area,
          badge: t('outputs.categories.groups'),
          badgeClass: 'badge-secondary',
          disabled: !saved,
          disabledLabel: !saved ? t('common.unsaved') : undefined,
        };
      });

    return [...outputs, ...groups];
  }, [allOutputs, allOutputGroups, savedOutputs, savedOutputGroups]);

  return (
    <>
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.output')}</span>
        </label>
        <SearchableEntityPicker
          value={action.boneio_output || action.pin || ''}
          onChange={(value: string) => handleUpdate('boneio_output', value)}
          items={outputItems}
          allAreas={allAreas}
          placeholder={t('event_form.select_output')}
          recentKey="outputs"
          preferredArea={preferredArea}
        />
      </div>

      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.action_output')}</span>
        </label>
        <Select
          value={action.action_output || 'TOGGLE'}
          onValueChange={(value) => onUpdate('action_output', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select action..." />
          </SelectTrigger>
          <SelectContent>
            {OUTPUT_ONLY_ACTIONS.map((option: string) => (
              <SelectItem key={option} value={option}>
                {formatActionLabel(option, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </>
  );
};

export default OutputAction;
