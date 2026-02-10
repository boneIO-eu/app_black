import React from 'react';
import { FaTrash } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import type { CoverEntity, OutputEntity } from '@/types/config';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';

// Import sub-components
import {
  validateAction as validate,
  OutputAction,
  CoverAction,
  MqttAction,
  OutputOverMqttAction,
  CoverOverMqttAction,
  RemoteOutputAction,
  RemoteCoverAction,
} from './ActionFields/index';
import type { Area, RemoteDevice } from './ActionFields/types';

// Re-export validation function for use in parent components
export const validateAction = validate;

interface ActionFieldsProps {
  action: any;
  index: number;
  onUpdate: (field: string, value: any) => void;
  onRemove: () => void;
  allOutputs: OutputEntity[];
  allOutputGroups: any[];
  allCovers: CoverEntity[];
  allAreas: Area[];
  allRemoteDevices?: RemoteDevice[];
  actionTypeOptions: string[];
  actionOutputOptions: string[];
  actionCoverOptions: string[];
  showValidation?: boolean;
  savedOutputs?: OutputEntity[];
  savedOutputGroups?: any[];
  savedCovers?: CoverEntity[];
  clickType?: 'single' | 'double' | 'triple' | 'long' | 'double_then_long' | 'single_then_long' | 'double_then_single' | 'pressed' | 'released';
}

/**
 * ActionFields component - renders form fields for configuring actions.
 * Supports multiple action types: output, cover, mqtt, output_over_mqtt, cover_over_mqtt, remote_output, remote_cover.
 */
const ActionFields: React.FC<ActionFieldsProps> = ({
  action,
  index,
  onUpdate,
  onRemove,
  allOutputs,
  allOutputGroups,
  allCovers,
  allAreas,
  allRemoteDevices = [],
  actionTypeOptions,
  actionOutputOptions,
  actionCoverOptions,
  showValidation = false,
  savedOutputs,
  savedOutputGroups,
  savedCovers,
  clickType,
}) => {
  const { t } = useTranslation();
  const actionType = action.action || 'output';
  const isLongPress = clickType === 'long' || clickType === 'double_then_long' || clickType === 'single_then_long';
  const hasDurationThresholds = !!(action.min_duration || action.max_duration);
  const hasRepeat = !!action.repeat;

  const validationError = showValidation ? validateAction(action, t) : null;

  /**
   * Checks if a cover is saved (committed) and can be selected.
   */
  const isCoverSaved = (coverId: string): boolean => {
    if (!savedCovers) return true;
    return savedCovers.some((c: any) => c.id === coverId || c === coverId);
  };

  return (
    <div className="border border-base-300 rounded-lg p-4 mb-3 bg-base-100">
      <div className="flex justify-between items-center mb-3">
        <span className="font-medium">{t('event_form.action')} {index + 1}</span>
        <button
          type="button"
          className="btn btn-ghost btn-sm text-error"
          onClick={onRemove}
        >
          <FaTrash />
        </button>
      </div>

      {validationError && (
        <div className="alert alert-error mb-3 py-2">
          <span className="text-sm">{validationError}</span>
        </div>
      )}

      {/* Action Type Selection */}
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.action_type')}</span>
        </label>
        <Select
          value={actionType}
          onValueChange={(value) => onUpdate('action', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('event_form.select_action_type')} />
          </SelectTrigger>
          <SelectContent>
            {actionTypeOptions.map((opt: string) => (
              <SelectItem key={opt} value={opt}>
                {opt.split('_').map(word =>
                  word.charAt(0).toUpperCase() + word.slice(1)
                ).join(' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Cover Action (local) */}
      {actionType === 'cover' && (
        <CoverAction
          action={action}
          onUpdate={onUpdate}
          t={t}
          allCovers={allCovers}
          allAreas={allAreas}
          actionCoverOptions={actionCoverOptions}
          savedCovers={savedCovers}
          isCoverSaved={isCoverSaved}
        />
      )}

      {/* Output Action (local) */}
      {actionType === 'output' && (
        <OutputAction
          action={action}
          onUpdate={onUpdate}
          t={t}
          allOutputs={allOutputs}
          allOutputGroups={allOutputGroups}
          actionOutputOptions={actionOutputOptions}
          savedOutputs={savedOutputs}
          savedOutputGroups={savedOutputGroups}
        />
      )}

      {/* MQTT Action */}
      {actionType === 'mqtt' && (
        <MqttAction
          action={action}
          onUpdate={onUpdate}
          t={t}
        />
      )}

      {/* Output Over MQTT Action */}
      {actionType === 'output_over_mqtt' && (
        <OutputOverMqttAction
          action={action}
          onUpdate={onUpdate}
          t={t}
          allOutputs={allOutputs}
          allOutputGroups={allOutputGroups}
          actionOutputOptions={actionOutputOptions}
        />
      )}

      {/* Cover Over MQTT Action */}
      {actionType === 'cover_over_mqtt' && (
        <CoverOverMqttAction
          action={action}
          onUpdate={onUpdate}
          t={t}
          allCovers={allCovers}
          allAreas={allAreas}
          actionCoverOptions={actionCoverOptions}
        />
      )}

      {/* Remote Output Action (ESPHome, WLED, MQTT) */}
      {actionType === 'remote_output' && (
        <RemoteOutputAction
          action={action}
          onUpdate={onUpdate}
          t={t}
          allRemoteDevices={allRemoteDevices}
          actionOutputOptions={actionOutputOptions}
        />
      )}

      {/* Remote Cover Action (ESPHome, MQTT) */}
      {actionType === 'remote_cover' && (
        <RemoteCoverAction
          action={action}
          onUpdate={onUpdate}
          t={t}
          allRemoteDevices={allRemoteDevices}
          actionCoverOptions={actionCoverOptions}
        />
      )}

      {/* Duration thresholds - only for long press actions, hidden when repeat is enabled */}
      {isLongPress && !hasRepeat && (
        <div className="form-control mb-3">
          <label className="label">
            <span className="label-text font-medium">{t('event_form.duration_thresholds')}</span>
            <span className="label-text-alt">{t('event_form.duration_thresholds_hint')}</span>
          </label>
          <div className="flex gap-2">
            <div className="flex-1">
              <input
                type="number"
                placeholder={t('event_form.min_duration_ms')}
                className="input input-bordered w-full"
                value={action.min_duration || ''}
                onChange={(e) => onUpdate('min_duration', e.target.value ? parseInt(e.target.value) : undefined)}
                min="0"
              />
            </div>
            <div className="flex-1">
              <input
                type="number"
                placeholder={t('event_form.max_duration_ms')}
                className="input input-bordered w-full"
                value={action.max_duration || ''}
                onChange={(e) => onUpdate('max_duration', e.target.value ? parseInt(e.target.value) : undefined)}
                min="0"
              />
            </div>
          </div>
        </div>
      )}

      {/* Repeat on hold - only for long press actions, hidden when duration thresholds are set */}
      {isLongPress && !hasDurationThresholds && (
        <div className="form-control mb-3">
          <label className="label cursor-pointer justify-start gap-3">
            <input
              type="checkbox"
              className="checkbox checkbox-primary"
              checked={action.repeat || false}
              onChange={(e) => {
                onUpdate('repeat', e.target.checked || undefined);
                if (!e.target.checked) {
                  onUpdate('repeat_interval', undefined);
                }
              }}
            />
            <div>
              <span className="label-text font-medium">{t('event_form.repeat_on_hold')}</span>
              <p className="label-text-alt text-xs opacity-70">{t('event_form.repeat_on_hold_hint')}</p>
            </div>
          </label>
          {action.repeat && (
            <div className="mt-2">
              <SimpleTimePeriodInput
                value={action.repeat_interval ?? '800ms'}
                onChange={(val) => onUpdate('repeat_interval', val)}
                label={t('event_form.repeat_interval_ms')}
                minimum={200}
                allowedUnits={['ms', 's']}
              />
              <label className="label">
                <span className="label-text-alt text-xs">{t('event_form.repeat_interval_hint')}</span>
              </label>
            </div>
          )}
        </div>
      )}

    </div>
  );
};

export default ActionFields;
