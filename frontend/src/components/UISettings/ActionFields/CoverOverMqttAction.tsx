import React from 'react';
import { NumericInput } from '@/components/ui/NumericInput';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { sanitizeId } from '../helpers/idValidation';
import type { CoverOverMqttActionProps } from './types';
import { formatActionLabel } from './helpers';

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
                {formatActionLabel(option, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Tilt position input — required for TILT action */}
      {action.action_cover === 'TILT' && (
        <div className="form-control mb-3">
          <label className="label">
            <span className="label-text font-medium">{t('event_form.tilt_position')} <span className="text-error">*</span></span>
          </label>
          <NumericInput
            className={(action.data?.tilt_position === undefined || action.data?.tilt_position === null || action.data?.tilt_position === '') ? 'input-error' : ''}
            min={0}
            max={100}
            placeholder="50"
            value={action.data?.tilt_position ?? ''}
            onChange={(v) => {
              const data = { ...(action.data || {}), tilt_position: v === '' ? undefined : v };
              onUpdate('data', data);
            }}
          />
          <label className="label">
            <span className="label-text-alt">{t('event_form.tilt_position_hint')}</span>
          </label>
        </div>
      )}

      {action.action_cover === 'SMART_TOGGLE' && (
        <div className="form-control mb-3">
          <label className="label">
            <span className="label-text font-medium">{t('event_form.always_open_till')}</span>
          </label>
          <NumericInput
            min={0}
            max={100}
            placeholder="50"
            value={action.data?.always_open_till ?? 50}
            onChange={(v) => {
              const data = { ...(action.data || {}), always_open_till: v === '' ? 50 : v };
              onUpdate('data', data);
            }}
          />
          <label className="label">
            <span className="label-text-alt">{t('event_form.always_open_till_hint')}</span>
          </label>
        </div>
      )}
    </>
  );
};

export default CoverOverMqttAction;
