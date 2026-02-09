import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { sanitizeId } from '../helpers/idValidation';
import type { CoverOverMqttActionProps } from './types';

/**
 * Cover Over MQTT Action component - controls covers on remote boneIO devices via MQTT.
 */
const CoverOverMqttAction: React.FC<CoverOverMqttActionProps> = ({
  action,
  onUpdate,
  t,
  actionCoverOptions,
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
          <span className="label-text font-medium">{t('event_form.cover_id')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          placeholder={t('event_form.cover_id_placeholder')}
          value={action.boneio_cover || action.pin || ''}
          onChange={(e) => handleUpdate('boneio_cover', e.target.value)}
        />
        <label className="label">
          <span className="label-text-alt">{t('event_form.cover_id_hint')}</span>
        </label>
      </div>

      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.cover_action')}</span>
        </label>
        <Select
          value={action.action_cover || 'TOGGLE'}
          onValueChange={(value) => onUpdate('action_cover', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select action..." />
          </SelectTrigger>
          <SelectContent>
            {actionCoverOptions.map((option: string) => (
              <SelectItem key={option} value={option}>
                {option.split('_').map(word => 
                  word.charAt(0) + word.slice(1).toLowerCase()
                ).join(' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </>
  );
};

export default CoverOverMqttAction;
