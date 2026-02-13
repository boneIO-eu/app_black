import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import OutputSelectDropdown from '../OutputSelectDropdown';
import type { OutputActionProps } from './types';
import { formatActionLabel } from './helpers';

/**
 * Output Action component - handles local boneIO outputs.
 */
const OutputAction: React.FC<OutputActionProps> = ({
  action,
  onUpdate,
  t,
  allOutputs,
  allOutputGroups,
  actionOutputOptions,
  savedOutputs,
  savedOutputGroups,
}) => {
  // Wrapper for onUpdate that removes deprecated 'pin' field
  const handleUpdate = (field: string, value: any) => {
    if (action.pin) {
      onUpdate('pin', undefined);
    }
    onUpdate(field, value);
  };

  return (
    <>
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.output')}</span>
        </label>
        <OutputSelectDropdown
          value={action.boneio_output || action.pin || ''}
          onChange={(value: string) => handleUpdate('boneio_output', value)}
          allOutputs={[
            ...allOutputs.filter((output: any) => output && typeof output === 'object' && output.output_type?.toLowerCase() !== 'cover' && (output.id || output.boneio_output)),
            ...allOutputGroups.filter((group: any) => group && typeof group === 'object' && group.id).map((group: any) => ({
              ...group,
              id: group.id,
              name: group.name || group.id,
              isGroup: true
            }))
          ]}
          allAreas={[]}
          placeholder={t('event_form.select_output')}
          savedOutputs={savedOutputs}
          savedOutputGroups={savedOutputGroups}
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
            {actionOutputOptions.map((option: string) => (
              <SelectItem key={option} value={option}>
                {formatActionLabel(option)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </>
  );
};

export default OutputAction;
