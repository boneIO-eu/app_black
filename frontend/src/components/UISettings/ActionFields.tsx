import React, { useState } from 'react';
import { NumericInput } from '@/components/ui/NumericInput';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { FaTrash, FaPlay, FaLightbulb, FaCloud, FaWifi, FaSort } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import axios from '@/api/axios';
import type { CoverEntity, OutputEntity, BinarySensorEntity } from '@/types/config';
import ActionConditions from './ActionFields/ActionConditions';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';

// Helper to render distinct theme icons for each action type
const getActionTypeIcon = (type: string) => {
  switch (type) {
    case 'output':
      return <FaLightbulb className="text-amber-500 shrink-0 text-sm" />;
    case 'cover':
      return <FaSort className="text-blue-500 shrink-0 text-sm" />;
    case 'mqtt':
      return <FaCloud className="text-info shrink-0 text-sm" />;
    case 'output_over_mqtt':
      return (
        <div className="flex gap-0.5 items-center shrink-0">
          <FaCloud className="text-info text-[10px]" />
          <FaLightbulb className="text-amber-500 text-[10px]" />
        </div>
      );
    case 'cover_over_mqtt':
      return (
        <div className="flex gap-0.5 items-center shrink-0">
          <FaCloud className="text-info text-[10px]" />
          <FaSort className="text-blue-500 text-[10px]" />
        </div>
      );
    case 'remote_output':
      return (
        <div className="flex gap-0.5 items-center shrink-0">
          <FaWifi className="text-success text-[10px]" />
          <FaLightbulb className="text-amber-500 text-[10px]" />
        </div>
      );
    case 'remote_cover':
      return (
        <div className="flex gap-0.5 items-center shrink-0">
          <FaWifi className="text-success text-[10px]" />
          <FaSort className="text-blue-500 text-[10px]" />
        </div>
      );
    default:
      return null;
  }
};

// Import sub-components
import {
  validateAction as validate,
  cleanActionFields as cleanFields,
  OutputAction,
  CoverAction,
  MqttAction,
  OutputOverMqttAction,
  CoverOverMqttAction,
  RemoteOutputAction,
  RemoteCoverAction,
} from './ActionFields/index';
import type { Area, RemoteDevice } from './ActionFields/types';

// Re-export helper functions for use in parent components
export const validateAction = validate;
export const cleanActionFields = cleanFields;

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
  allBinarySensors?: BinarySensorEntity[];
  /** Remote inputs (binary sensors from ESPHome/CAN devices) for condition entity selection */
  allRemoteInputs?: Array<Record<string, unknown>>;
  /** Entity ID to exclude from condition binary_sensor list (prevents self-reference) */
  excludeEntityId?: string;
  /** Area ID of the input being configured — used to prioritize same-area entities in pickers. */
  preferredArea?: string;
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
  allBinarySensors = [],
  allRemoteInputs = [],
  excludeEntityId,
  preferredArea,
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

  const [testStatus, setTestStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [testError, setTestError] = useState<string | null>(null);

  /**
   * Execute the current action via the test-action API endpoint.
   * Uses the same code path as real button presses on the backend.
   */
  const handleTestAction = async () => {
    setTestStatus('loading');
    setTestError(null);
    try {
      await axios.post('/api/test-action', { action });
      setTestStatus('success');
      setTimeout(() => setTestStatus('idle'), 2000);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err.message || 'Unknown error';
      setTestError(detail);
      setTestStatus('error');
      setTimeout(() => { setTestStatus('idle'); setTestError(null); }, 4000);
    }
  };

  return (
    <div className="border border-base-300 rounded-lg p-4 mb-3 bg-base-100">
      <div className="flex justify-between items-center mb-3">
        <span className="font-medium">{t('event_form.action')} {index + 1}</span>
        <div className="flex items-center gap-1">
          {testStatus === 'success' && (
            <span className="text-success text-xs font-medium mr-1">{t('event_form.test_action_success')}</span>
          )}
          {testStatus === 'error' && (
            <span className="text-error text-xs font-medium mr-1" title={testError || ''}>{t('event_form.test_action_error')}</span>
          )}
          <button
            type="button"
            className={`btn btn-ghost btn-sm ${
              testStatus === 'success' ? 'text-success' :
              testStatus === 'error' ? 'text-error' :
              'text-info'
            }`}
            onClick={handleTestAction}
            disabled={testStatus === 'loading' || !!validationError}
            title={t('event_form.test_action')}
          >
            {testStatus === 'loading' ? (
              <span className="loading loading-spinner loading-xs"></span>
            ) : (
              <FaPlay className="w-3 h-3" />
            )}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm text-error"
            onClick={onRemove}
          >
            <FaTrash />
          </button>
        </div>
      </div>

      {validationError && (
        <div className="alert alert-error mb-3 py-2">
          <span className="text-sm">{validationError}</span>
        </div>
      )}

      {/* Action Type Selection */}
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-semibold">{t('event_form.action_type')}</span>
        </label>
        <Select
          value={actionType}
          onValueChange={(value) => onUpdate('action', value)}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('event_form.action_type')}>
              {(val: string | null) => {
                if (!val) return t('event_form.action_type');
                const typeKey = `actions.type_${val}`;
                const translated = t(typeKey);
                const label = translated !== typeKey
                  ? translated
                  : val.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                return (
                  <span className="flex items-center gap-2">
                    {getActionTypeIcon(val)}
                    {label}
                  </span>
                );
              }}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {actionTypeOptions.map((opt: string) => {
              const typeKey = `actions.type_${opt}`;
              const translated = t(typeKey);
              const label = translated !== typeKey
                ? translated
                : opt.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
              return (
                <SelectItem key={opt} value={opt}>
                  <span className="flex items-center gap-2">
                    {getActionTypeIcon(opt)}
                    {label}
                  </span>
                </SelectItem>
              );
            })}
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
          preferredArea={preferredArea}
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
          allAreas={allAreas}
          actionOutputOptions={actionOutputOptions}
          savedOutputs={savedOutputs}
          savedOutputGroups={savedOutputGroups}
          preferredArea={preferredArea}
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
              <NumericInput
                placeholder={t('event_form.min_duration_ms')}
                value={action.min_duration || ''}
                onChange={(v) => onUpdate('min_duration', v === '' ? undefined : v)}
                min={0}
              />
            </div>
            <div className="flex-1">
              <NumericInput
                placeholder={t('event_form.max_duration_ms')}
                value={action.max_duration || ''}
                onChange={(v) => onUpdate('max_duration', v === '' ? undefined : v)}
                min={0}
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

      {/* Delay before execution — only for pressed/released (binary sensor) actions */}
      {(clickType === 'pressed' || clickType === 'released') && (
        <div className="form-control mb-3">
          <label className="label cursor-pointer justify-start gap-3">
            <input
              type="checkbox"
              className="checkbox checkbox-primary"
              checked={!!action.delay}
              onChange={(e) => {
                if (e.target.checked) {
                  onUpdate('__batch', { delay: '2min', delay_cancel_on: [clickType === 'released' ? 'pressed' : 'released'] });
                } else {
                  onUpdate('__batch', { delay: undefined, delay_cancel_on: undefined });
                }
              }}
            />
            <div>
              <span className="label-text font-medium">{t('actions.delay_execution')}</span>
              <p className="label-text-alt text-xs opacity-70">{t('actions.delay_execution_hint')}</p>
            </div>
          </label>
          {action.delay && (
            <div className="mt-2 ml-8 space-y-3">
              <SimpleTimePeriodInput
                value={action.delay}
                onChange={(val) => onUpdate('delay', val)}
                label={t('actions.delay_time')}
                minimum={1}
                allowedUnits={['s', 'min']}
              />
              <div>
                <label className="label py-0">
                  <span className="label-text text-sm font-medium">{t('actions.delay_cancel_on')}</span>
                </label>
                <p className="text-xs opacity-60 mb-2 ml-1">{t('actions.delay_cancel_on_hint')}</p>
                <div className="flex flex-wrap gap-2 ml-1">
                  {['pressed', 'released'].map((evt) => (
                    <label key={evt} className="label cursor-pointer gap-1.5 p-0">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-xs checkbox-primary"
                        checked={(action.delay_cancel_on || []).includes(evt)}
                        onChange={(e) => {
                          const current: string[] = action.delay_cancel_on || [];
                          const updated = e.target.checked
                            ? [...current, evt]
                            : current.filter((v: string) => v !== evt);
                          onUpdate('delay_cancel_on', updated.length > 0 ? updated : undefined);
                        }}
                      />
                      <span className="label-text text-xs">{t(`actions.event_${evt}`)}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Conditions — available for all action types */}
      <ActionConditions
        action={action}
        onUpdate={onUpdate}
        t={t}
        allOutputs={allOutputs}
        allCovers={allCovers}
        allBinarySensors={allBinarySensors}
        allRemoteInputs={allRemoteInputs}
        allAreas={allAreas}
        showValidation={showValidation}
        excludeEntityId={excludeEntityId}
      />

    </div>
  );
};

export default ActionFields;
