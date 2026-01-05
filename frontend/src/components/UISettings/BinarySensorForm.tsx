import React, { useState } from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import ActionFields, { validateAction } from './ActionFields';
import { TabsBox } from '@/components/ui/tabs-box';
import type { CoverEntity, OutputEntity } from '@/types/config';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface Action {
  action: string;
  /** Output ID to control (for output action) */
  boneio_output?: string;
  /** Cover ID to control (for cover action) */
  boneio_cover?: string;
  /** @deprecated Use boneio_output or boneio_cover instead */
  pin?: string;
  topic?: string;
  action_cover?: string;
  action_output?: string;
  action_mqtt_msg?: string;
  boneio_id?: string;
  data?: {
    position?: number;
    tilt_position?: number;
  };
}

interface BinarySensorData {
  name?: string;
  pin?: string;
  boneio_input?: string;
  bounce_time?: string | number;
  show_in_ha?: boolean;
  inverted?: boolean;
  initial_send?: boolean;
  clear_message?: boolean;
  device_class?: string;
  area?: string;
  actions?: {
    pressed?: Action[];
    released?: Action[];
  };
}

interface Area {
  id: string;
  name: string;
}

interface RemoteDevice {
  id: string;
  name?: string;
  protocol?: string;
  mqtt?: {
    outputs?: { id: string; name?: string }[];
    covers?: { id: string; name?: string }[];
  };
  esphome_api?: {
    host?: string;
    switches?: { id: string; name?: string; key?: number }[];
    lights?: { id: string; name?: string; key?: number; supports_brightness?: boolean }[];
    covers?: { id: string; name?: string; key?: number }[];
  };
}

interface BinarySensorFormProps {
  data: BinarySensorData;
  onChange: (data: BinarySensorData) => void;
  onSave: () => void;
  onCancel: () => void;
  isNew: boolean;
  schema?: any;
  allBinarySensors?: any[];
  allEvents?: any[];
  editingIndex?: number | null;
  allOutputs?: OutputEntity[];
  allOutputGroups?: any[];
  allCovers?: CoverEntity[];
  allAreas?: Area[];
  allRemoteDevices?: RemoteDevice[];
  onValidationChange?: (hasErrors: boolean) => void;
  /** Whether user attempted to submit (shows validation errors) */
  attemptedSubmit?: boolean;
  /** Saved (committed) outputs for comparison */
  savedOutputs?: any[];
  /** Saved (committed) output groups for comparison */
  savedOutputGroups?: any[];
  /** Saved (committed) covers for comparison */
  savedCovers?: any[];
}

const BinarySensorForm: React.FC<BinarySensorFormProps> = ({
  data,
  onChange,
  schema,
  allBinarySensors = [],
  allEvents = [],
  allOutputs = [],
  allOutputGroups = [],
  allCovers = [],
  allAreas = [],
  allRemoteDevices = [],
  editingIndex,
  onValidationChange,
  attemptedSubmit = false,
  savedOutputs,
  savedOutputGroups,
  savedCovers
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'pressed' | 'released'>('basic');

  // Get all validation errors
  const getValidationErrors = (): string[] => {
    const errors: string[] = [];
    
    ['pressed', 'released'].forEach((type) => {
      const actions = data.actions?.[type as 'pressed' | 'released'] || [];
      actions.forEach((action: Action, index: number) => {
        const error = validateAction(action, t);
        if (error) {
          errors.push(`${type.charAt(0).toUpperCase() + type.slice(1)} action ${index + 1}: ${error}`);
        }
      });
    });
    
    return errors;
  };

  const validationErrors = getValidationErrors();
  
  // Notify parent about validation status
  React.useEffect(() => {
    onValidationChange?.(validationErrors.length > 0);
  }, [validationErrors.length, onValidationChange]);

  // Extract enum values from schema
  const deviceClassOptions = schema?.items?.properties?.device_class?.enum || [
    'battery', 'battery_charging', 'carbon_monoxide', 'cold', 'connectivity',
    'door', 'garage_door', 'gas', 'heat', 'light', 'lock', 'moisture',
    'motion', 'moving', 'occupancy', 'opening', 'plug', 'power', 'presence',
    'problem', 'running', 'safety', 'smoke', 'sound', 'tamper', 'vibration', 'window'
  ];

  const allBoneioInputs = schema?.items?.properties?.boneio_input?.enum || [];
  
  // Filter out already used inputs from both binary_sensor and event (except current one)
  const usedInputsFromBinarySensors = allBinarySensors
    .filter((sensor, index) => {
      // Skip current item being edited
      if (editingIndex !== null && index === editingIndex) {
        return false;
      }
      // For new items, just filter out any used inputs
      return sensor.boneio_input && sensor !== data;
    })
    .map(sensor => sensor.boneio_input);
  
  const usedInputsFromEvents = allEvents
    .filter(event => event.boneio_input)
    .map(event => event.boneio_input);
  
  const usedInputs = [...new Set([...usedInputsFromBinarySensors, ...usedInputsFromEvents])];
  
  const availableInputs = allBoneioInputs.filter((input: string) => !usedInputs.includes(input));
  
  // If current input is used by this item, include it in options
  const currentInput = data.boneio_input;
  const boneioInputOptions = currentInput && !availableInputs.includes(currentInput)
    ? [...new Set([currentInput, ...availableInputs])].sort()
    : availableInputs;

  const actionTypeOptions = schema?.items?.properties?.actions?.properties?.pressed?.items?.properties?.action?.enum || [
    'mqtt', 'output', 'cover', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover'
  ];

  const actionOutputOptions = schema?.items?.properties?.actions?.properties?.pressed?.items?.properties?.action_output?.enum || [
    'TOGGLE', 'ON', 'OFF'
  ];

  const actionCoverOptions = schema?.items?.properties?.actions?.properties?.pressed?.items?.properties?.action_cover?.enum || [
    'TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE'
  ];

  const updateField = (field: keyof BinarySensorData, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const updateAction = (type: 'pressed' | 'released', index: number, field: string, value: any) => {
    const actions = { ...data.actions };
    if (!actions[type]) actions[type] = [];
    const updatedActions = [...actions[type]!];
    
    // When changing action type, clear pin field to avoid mismatched values
    if (field === 'action') {
      const currentAction = updatedActions[index];
      updatedActions[index] = {
        action: value,
        // Keep only fields that are common across all action types
        ...(currentAction?.boneio_id && { boneio_id: currentAction.boneio_id })
      };
    } else {
      // When setting new boneio_output or boneio_cover, remove old pin field
      if (field === 'boneio_output' || field === 'boneio_cover') {
        const currentAction = updatedActions[index];
        if (currentAction?.pin) {
          const { pin, ...rest } = currentAction;
          updatedActions[index] = { ...rest, [field]: value };
        } else {
          updatedActions[index] = { ...updatedActions[index], [field]: value };
        }
      } else {
        updatedActions[index] = { ...updatedActions[index], [field]: value };
      }
    }
    
    actions[type] = updatedActions;
    onChange({ ...data, actions });
  };

  const addAction = (type: 'pressed' | 'released') => {
    const actions = { ...data.actions };
    if (!actions[type]) actions[type] = [];
    const updatedActions = [...actions[type]!];
    updatedActions.push({ action: 'output' });
    actions[type] = updatedActions;
    onChange({ ...data, actions });
  };

  const removeAction = (type: 'pressed' | 'released', index: number) => {
    const actions = { ...data.actions };
    if (!actions[type]) return;
    actions[type] = actions[type]!.filter((_, i) => i !== index);
    onChange({ ...data, actions });
  };

  const renderActionFields = (action: Action, type: 'pressed' | 'released', index: number) => {
    return (
      <ActionFields
        key={index}
        action={action}
        index={index}
        onUpdate={(field, value) => updateAction(type, index, field, value)}
        onRemove={() => removeAction(type, index)}
        allOutputs={allOutputs}
        allOutputGroups={allOutputGroups}
        allCovers={allCovers}
        allAreas={allAreas}
        allRemoteDevices={allRemoteDevices}
        actionTypeOptions={actionTypeOptions}
        actionOutputOptions={actionOutputOptions}
        actionCoverOptions={actionCoverOptions}
        showValidation={attemptedSubmit}
        savedOutputs={savedOutputs}
        savedOutputGroups={savedOutputGroups}
        savedCovers={savedCovers}
      />
    );
  };

  return (
    <div className="space-y-4">
      {/* Validation Errors - sticky at top - pokazuj tylko gdy użytkownik próbował zapisać */}
      {attemptedSubmit && validationErrors.length > 0 && (
        <div className="alert alert-error sticky top-0 z-10 shadow-lg">
          <div>
            <h3 className="font-bold">{t('validation.errors')} ({validationErrors.length}):</h3>
            <ul className="list-disc list-inside max-h-24 overflow-y-auto">
              {validationErrors.map((error, index) => (
                <li key={index}>{error}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <TabsBox
        name="binary_sensor_tabs"
        activeTab={activeTab}
        onTabChange={(tabId) => setActiveTab(tabId as 'basic' | 'pressed' | 'released')}
        tabs={[
          {
            id: 'basic',
            label: t('settings.basic_settings'),
            content: (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('outputs.display_name')}</span>
                    </label>
                    <input
                      type="text"
                      className="input w-full"
                      placeholder={t('sensors.name_placeholder')}
                      value={data.name || ''}
                      onChange={(e) => updateField('name', e.target.value)}
                    />
                    <label className="label">
                      <span className="label-text-alt">{t('common.optional')}</span>
                    </label>
                  </div>

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('inputs.boneio_input')}</span>
                    </label>
                    <Select
                      value={data.boneio_input || ''}
                      onValueChange={(value) => updateField('boneio_input', value)}
                    >
                      <SelectTrigger className={`w-full uppercase ${usedInputs.length > 0 && boneioInputOptions.length === 0 ? 'border-warning' : ''}`}>
                        <SelectValue placeholder={t('inputs.select_input')} />
                      </SelectTrigger>
                      <SelectContent>
                        {boneioInputOptions.map((input: string) => (
                          <SelectItem key={input} value={input}>
                            {input}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {usedInputs.length > 0 && boneioInputOptions.length === 1 && (
                      <label className="label max-w-full">
                        <span className="label-text-alt text-warning whitespace-normal break-all">
                          {t('inputs.all_inputs_used')}
                        </span>
                      </label>
                    )}
                    {usedInputs.length > 0 && (
                      <label className="label max-w-full">
                        <span className="label-text-alt text-info whitespace-normal break-all">
                          {t('inputs.used_inputs')}: {usedInputs.length > 5 
                            ? `${usedInputs.slice(0, 3).join(', ')}, ... (+${usedInputs.length - 3} more)`
                            : usedInputs.join(', ')
                          }
                        </span>
                      </label>
                    )}
                  </div>

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('outputs.area')}</span>
                    </label>
                    <Select
                      value={data.area || '_none_'}
                      onValueChange={(value) => updateField('area', value === '_none_' ? undefined : value)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t('outputs.no_area')} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none_">{t('outputs.no_area')}</SelectItem>
                        {allAreas.map((area) => (
                          <SelectItem key={area.id} value={area.id}>
                            {area.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <label className="label">
                      <span className="label-text-alt">
                        {allAreas.length === 0 
                          ? t('outputs.area_empty_hint')
                          : t('outputs.area_hint')
                        }
                      </span>
                    </label>
                  </div>

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('inputs.bounce_time')} (ms)</span>
                    </label>
                    <input
                      type="number"
                      className="input w-full"
                      placeholder="120"
                      value={typeof data.bounce_time === 'number' ? data.bounce_time : 120}
                      onChange={(e) => updateField('bounce_time', parseInt(e.target.value) || 120)}
                    />
                    <label className="label">
                      <span className="label-text-alt">{t('inputs.bounce_time_hint')}</span>
                    </label>
                  </div>

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('inputs.device_class')}</span>
                    </label>
                    <Select
                      value={data.device_class || '_none_'}
                      onValueChange={(value) => updateField('device_class', value === '_none_' ? '' : value)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t('inputs.none')} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="_none_">{t('inputs.none')}</SelectItem>
                        {deviceClassOptions.map((deviceClass: string) => (
                          <SelectItem key={deviceClass} value={deviceClass}>
                            {deviceClass.split('_').map(word => 
                              word.charAt(0).toUpperCase() + word.slice(1)
                            ).join(' ')}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="divider">{t('settings.options')}</div>

                <div className="grid grid-cols-1 gap-4">
                  <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
                    <legend className="fieldset-legend">{t('inputs.show_in_ha')}</legend>
                    <label className="label cursor-pointer justify-start gap-4">
                      <input
                        type="checkbox"
                        className="toggle toggle-primary"
                        checked={data.show_in_ha !== false}
                        onChange={(e) => updateField('show_in_ha', e.target.checked)}
                      />
                      <span className="label-text wrap-break-word">{t('inputs.show_in_ha_hint')}</span>
                    </label>
                  </fieldset>

                  <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
                    <legend className="fieldset-legend">{t('inputs.inverted')}</legend>
                    <label className="label cursor-pointer justify-start gap-4">
                      <input
                        type="checkbox"
                        className="toggle toggle-primary"
                        checked={data.inverted === true}
                        onChange={(e) => updateField('inverted', e.target.checked)}
                      />
                      <span className="label-text">{t('inputs.inverted_hint')}</span>
                    </label>
                  </fieldset>

                  <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
                    <legend className="fieldset-legend">{t('inputs.initial_send')}</legend>
                    <label className="label cursor-pointer justify-start gap-4">
                      <input
                        type="checkbox"
                        className="toggle toggle-primary"
                        checked={data.initial_send === true}
                        onChange={(e) => updateField('initial_send', e.target.checked)}
                      />
                      <span className="label-text">{t('inputs.initial_send_hint')}</span>
                    </label>
                  </fieldset>

                  <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
                    <legend className="fieldset-legend">{t('inputs.clear_message')}</legend>
                    <label className="label cursor-pointer justify-start gap-4">
                      <input
                        type="checkbox"
                        className="toggle toggle-primary"
                        checked={data.clear_message === true}
                        onChange={(e) => updateField('clear_message', e.target.checked)}
                      />
                      <span className="label-text">{t('inputs.clear_message_hint')}</span>
                    </label>
                  </fieldset>
                </div>
              </div>
            ),
          },
          {
            id: 'pressed',
            label: t('inputs.pressed_actions'),
            badge: data.actions?.pressed?.length || undefined,
            content: (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-semibold">{t('inputs.pressed_actions')}</h3>
                  <button
                    type="button"
                    onClick={() => addAction('pressed')}
                    className="btn btn-primary btn-sm"
                  >
                    <FaPlus className="mr-2" />
                    {t('inputs.add_action')}
                  </button>
                </div>

                {data.actions?.pressed && data.actions.pressed.length > 0 ? (
                  data.actions.pressed.map((action, index) =>
                    renderActionFields(action, 'pressed', index)
                  )
                ) : (
                  <div className="text-center py-8 text-base-content/60">
                    <p>{t('inputs.no_pressed_actions')}</p>
                    <p className="text-sm">{t('inputs.click_add_action')}</p>
                  </div>
                )}
              </div>
            ),
          },
          {
            id: 'released',
            label: t('inputs.released_actions'),
            badge: data.actions?.released?.length || undefined,
            content: (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-semibold">{t('inputs.released_actions')}</h3>
                  <button
                    type="button"
                    onClick={() => addAction('released')}
                    className="btn btn-primary btn-sm"
                  >
                    <FaPlus className="mr-2" />
                    {t('inputs.add_action')}
                  </button>
                </div>

                {data.actions?.released && data.actions.released.length > 0 ? (
                  data.actions.released.map((action, index) =>
                    renderActionFields(action, 'released', index)
                  )
                ) : (
                  <div className="text-center py-8 text-base-content/60">
                    <p>{t('inputs.no_released_actions')}</p>
                    <p className="text-sm">{t('inputs.click_add_action')}</p>
                  </div>
                )}
              </div>
            ),
          },
        ]}
      />

    </div>
  );
};

export default BinarySensorForm;
