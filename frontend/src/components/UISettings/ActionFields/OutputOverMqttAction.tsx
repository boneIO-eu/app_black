import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { sanitizeId } from '../helpers/idValidation';
import type { OutputOverMqttActionProps } from './types';
import { formatActionLabel } from './helpers';

/** Output actions supported by light/switch outputs. */
const OUTPUT_ONLY_ACTIONS = ['TOGGLE', 'ON', 'OFF'];

/**
 * Output Over MQTT Action component - controls outputs on remote boneIO devices via MQTT.
 */
const OutputOverMqttAction: React.FC<OutputOverMqttActionProps> = ({
  action,
  onUpdate,
  t,
  actionOutputOptions: _actionOutputOptions,
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
          <span className="label-text font-medium">{t('event_form.boneio_id')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          placeholder={t('event_form.boneio_id_placeholder')}
          value={action.boneio_id || ''}
          onChange={(e) => onUpdate('boneio_id', sanitizeId(e.target.value))}
        />
        <label className="label">
          <span className="label-text-alt">{t('event_form.boneio_id_hint')}</span>
        </label>
      </div>

      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.output_id')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          placeholder={t('event_form.output_id_placeholder')}
          value={action.boneio_output || action.pin || ''}
          onChange={(e) => handleUpdate('boneio_output', e.target.value)}
        />
        <label className="label">
          <span className="label-text-alt">{t('event_form.output_id_hint')}</span>
        </label>
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

export default OutputOverMqttAction;
