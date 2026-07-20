import React, { useState } from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import { NumericInput } from '@/components/ui/NumericInput';
import ActionFields, { validateAction, cleanActionFields } from './ActionFields';
import AiConfigAssistant from './AiConfigAssistant';
import BlueprintPicker from './widgets/BlueprintPicker';
import { getInputAvailability, buildInputOptions } from './helpers/inputFilterUtils';
import { convertTimeperiodToMilliseconds } from './helpers/configSchemaUtils';
import AreaSelect from './widgets/AreaSelect';
import SettingsToggleGroup from './widgets/SettingsToggleGroup';
import { TabsBox } from '@/components/ui/tabs-box';
import type { 
  BinarySensorEntity, 
  CoverEntity, 
  OutputEntity, 
  AreaEntity,
  RemoteDeviceEntity,
  Action,
} from '@/types/config';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface BinarySensorFormProps {
  data: BinarySensorEntity;
  onChange: (data: BinarySensorEntity) => void;
  onSave: () => void;
  onCancel: () => void;
  isNew: boolean;
  schema?: any;
  allBinarySensors?: BinarySensorEntity[];
  allEvents?: any[];
  editingIndex?: number | null;
  allOutputs?: OutputEntity[];
  allOutputGroups?: any[];
  allCovers?: CoverEntity[];
  allAreas?: AreaEntity[];
  allRemoteDevices?: RemoteDeviceEntity[];
  /** Remote inputs for condition entity picker */
  allRemoteInputs?: Array<Record<string, unknown>>;
  onValidationChange?: (hasErrors: boolean) => void;
  /** Whether user attempted to submit (shows validation errors) */
  attemptedSubmit?: boolean;
  /** Saved (committed) outputs for comparison */
  savedOutputs?: OutputEntity[];
  /** Saved (committed) output groups for comparison */
  savedOutputGroups?: any[];
  /** Saved (committed) covers for comparison */
  savedCovers?: CoverEntity[];
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
  allRemoteInputs = [],
  editingIndex,
  onValidationChange,
  attemptedSubmit = false,
  savedOutputs,
  savedOutputGroups,
  savedCovers
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'pressed' | 'released'>('basic');
  const [showBlueprint, setShowBlueprint] = useState(false);

  /** Apply a blueprint patch — merges device_class and actions into current data */
  const applyBlueprint = (patch: Partial<BinarySensorEntity>) => {
    onChange({ ...data, ...patch });
    // Switch to pressed tab to show the result
    setActiveTab('pressed');
  };

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
  // Case-insensitive comparison — see inputFilterUtils.ts for details
  const { usedInputs, availableInputs } = getInputAvailability(
    allBoneioInputs, allBinarySensors, allEvents, editingIndex, 'binary_sensor',
  );
  const boneioInputOptions = buildInputOptions(availableInputs, data.boneio_input);

  const rawActionTypeOptions = schema?.items?.properties?.actions?.properties?.pressed?.items?.properties?.action?.enum || [
    'mqtt', 'output', 'cover', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover'
  ];
  // Deduplicate: schema may provide both uppercase and lowercase variants
  const actionTypeOptions = [...new Set(rawActionTypeOptions.map((o: string) => o.toLowerCase()))] as string[];

  const actionOutputOptions = schema?.items?.properties?.actions?.properties?.pressed?.items?.properties?.action_output?.enum || [
    'TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE', 'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET'
  ];

  const actionCoverOptions = schema?.items?.properties?.actions?.properties?.pressed?.items?.properties?.action_cover?.enum || [
    'TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE', 'SMART_TOGGLE', 'TILT', 'TILT_OPEN', 'TILT_CLOSE'
  ];

  const updateField = (field: keyof BinarySensorEntity, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const updateAction = (type: 'pressed' | 'released', index: number, field: string, value: any) => {
    const actions = { ...data.actions };
    if (!actions[type]) actions[type] = [];
    const updatedActions = [...actions[type]!];
    
    // When changing action type, clean fields to only keep valid ones for new type
    if (field === 'action') {
      const currentAction = updatedActions[index];
      updatedActions[index] = cleanActionFields(value, currentAction) as any;
    } else if (field === '__batch') {
      // Batch update: value is an object with multiple fields to set at once
      const current = { ...updatedActions[index] };
      for (const [k, v] of Object.entries(value)) {
        if (v === undefined) {
          delete (current as any)[k];
        } else {
          (current as any)[k] = v;
        }
      }
      updatedActions[index] = current;
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
      } else if (field === 'remote_device') {
        // Clear dependent fields when changing remote device
        updatedActions[index] = { ...updatedActions[index], [field]: value, output_id: undefined, cover_id: undefined, presets: undefined, colors: undefined };
      } else if (field === 'output_id') {
        // Clear presets/colors when changing output
        updatedActions[index] = { ...updatedActions[index], [field]: value, presets: undefined, colors: undefined };
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
        clickType={type}
        allBinarySensors={allBinarySensors}
        allRemoteInputs={allRemoteInputs}
        excludeEntityId={data.boneio_input}
        preferredArea={data.area}
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

      <AiConfigAssistant
        entityType="binary_sensor"
        data={data}
        schema={schema}
        allOutputs={allOutputs}
        allOutputGroups={allOutputGroups}
        allCovers={allCovers}
        allAreas={allAreas}
        allRemoteDevices={allRemoteDevices}
        actionTypeOptions={actionTypeOptions}
        actionOutputOptions={actionOutputOptions}
        actionCoverOptions={actionCoverOptions}
        onApply={onChange}
      />

      {/* Blueprint Picker — quick action config for common patterns */}
      <button
        type="button"
        className="w-full text-left p-3 rounded-lg border border-dashed border-primary/30 bg-primary/5 hover:bg-primary/10 hover:border-primary/50 transition-all duration-200 cursor-pointer group"
        onClick={() => setShowBlueprint(true)}
      >
        <div className="flex items-center gap-2">
          <span className="text-lg">🚀</span>
          <span className="font-medium text-sm text-primary">{t('blueprints.quick_setup')}</span>
        </div>
        <p className="text-xs text-base-content/50 mt-1 ml-7">{t('blueprints.quick_setup_hint')}</p>
      </button>

      {showBlueprint && (
        <BlueprintPicker
          onApply={applyBlueprint}
          onClose={() => setShowBlueprint(false)}
          allOutputs={allOutputs}
          allAreas={allAreas}
          savedOutputs={savedOutputs}
          savedOutputGroups={savedOutputGroups}
        />
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
                      placeholder={t('sensors.binary_sensor_name_placeholder')}
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

                  <AreaSelect
                    value={data.area}
                    onChange={(v) => updateField('area', v)}
                    areas={allAreas}
                  />

                  <div className="form-control">
                    <label className="label">
                      <span className="label-text font-medium">{t('inputs.bounce_time')} (ms)</span>
                    </label>
                    <NumericInput
                      placeholder="120"
                      value={convertTimeperiodToMilliseconds(data.bounce_time) || 120}
                      onChange={(v) => updateField('bounce_time', v === '' ? 120 : v)}
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

                <SettingsToggleGroup
                  items={[
                    {
                      key: 'show_in_ha',
                      label: t('inputs.show_in_ha'),
                      description: t('inputs.show_in_ha_hint'),
                      checked: data.show_in_ha !== false,
                      onChange: (checked) => updateField('show_in_ha', checked),
                    },
                    {
                      key: 'inverted',
                      label: t('inputs.inverted'),
                      description: t('inputs.inverted_hint'),
                      checked: data.inverted === true,
                      onChange: (checked) => updateField('inverted', checked),
                    },
                    {
                      key: 'initial_send',
                      label: t('inputs.initial_send'),
                      description: t('inputs.initial_send_hint'),
                      checked: data.initial_send === true,
                      onChange: (checked) => updateField('initial_send', checked),
                    },
                    {
                      key: 'clear_message',
                      label: t('inputs.clear_message'),
                      description: t('inputs.clear_message_hint'),
                      checked: data.clear_message === true,
                      onChange: (checked) => updateField('clear_message', checked),
                    },
                  ]}
                />
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
