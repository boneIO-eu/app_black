import React, { useState } from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import ActionFields, { validateAction, cleanActionFields } from './ActionFields';
import AiConfigAssistant from './AiConfigAssistant';
import { getInputAvailability, buildInputOptions } from './helpers/inputFilterUtils';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
import { convertTimeperiodToMilliseconds } from './helpers/configSchemaUtils';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { 
  EventEntity, 
  AreaEntity,
  OutputEntity,
  CoverEntity,
  BinarySensorEntity,
  RemoteDeviceEntity,
} from '@/types/config';

interface EventFormProps {
  /** Current event entity data being edited */
  data: EventEntity;
  /** Callback when data changes */
  onChange: (data: EventEntity) => void;
  /** Callback to save the form */
  onSave: () => void;
  /** Callback to cancel editing */
  onCancel: () => void;
  /** Whether this is a new entity */
  isNew: boolean;
  /** JSON Schema for validation */
  schema?: any;
  /** All binary sensors for input filtering */
  allBinarySensors?: BinarySensorEntity[];
  /** All events for input filtering */
  allEvents?: EventEntity[];
  /** Index of item being edited (null for new) */
  editingIndex?: number | null;
  /** All outputs for action dropdowns */
  allOutputs?: OutputEntity[];
  /** All output groups for action dropdowns */
  allOutputGroups?: any[];
  /** All covers for action dropdowns */
  allCovers?: CoverEntity[];
  /** All areas for area dropdown */
  allAreas?: AreaEntity[];
  /** All remote devices for remote action dropdowns */
  allRemoteDevices?: RemoteDeviceEntity[];
  /** Callback when validation state changes */
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

const EventForm: React.FC<EventFormProps> = ({ 
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
  const [activeTab, setActiveTab] = useState<'basic' | 'single' | 'double' | 'triple' | 'long' | 'sequences' | 'advanced'>('basic');

  // Extract enums from schema for dropdowns
  const allBoneioInputs = schema?.items?.properties?.boneio_input?.enum || [];
  
  // Filter out already used inputs from both binary_sensor and event (except current one)
  // Case-insensitive comparison — see inputFilterUtils.ts for details
  const { usedInputs, availableInputs } = getInputAvailability(
    allBoneioInputs, allBinarySensors, allEvents, editingIndex, 'event',
  );
  const boneioInputOptions = buildInputOptions(availableInputs, data.boneio_input);
  const actionTypeOptions = schema?.items?.properties?.actions?.properties?.single?.items?.properties?.action?.enum || [
    'mqtt', 'output', 'cover', 'output_over_mqtt', 'cover_over_mqtt', 'remote_output', 'remote_cover'
  ];
  const actionCoverOptions = schema?.items?.properties?.actions?.properties?.single?.items?.properties?.action_cover?.enum || [
    'TOGGLE', 'OPEN', 'CLOSE', 'STOP', 'TOGGLE_OPEN', 'TOGGLE_CLOSE', 'SMART_TOGGLE', 'TILT', 'TILT_OPEN', 'TILT_CLOSE'
  ];
  const actionOutputOptions = schema?.items?.properties?.actions?.properties?.single?.items?.properties?.action_output?.enum || [
    'TOGGLE', 'ON', 'OFF', 'BRIGHTNESS_UP', 'BRIGHTNESS_DOWN', 'BRIGHTNESS_UP_CYCLE', 'BRIGHTNESS_DOWN_CYCLE', 'SET_BRIGHTNESS', 'CYCLE_COLOR', 'CYCLE_PRESET'
  ];

  const updateField = (field: string, value: any) => {
    console.log('updateField', field, value, data);
    onChange({ ...data, [field]: value });
  };

  // Validate action using imported function

  // Get all validation errors
  const getValidationErrors = (): string[] => {
    const errors: string[] = [];
    
    ['single', 'double', 'triple', 'long', 'double_then_long', 'single_then_long', 'double_then_single'].forEach((type) => {
      const actions = data.actions?.[type] || [];
      actions.forEach((action: any, index: number) => {
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

  const updateAction = (actionType: 'single' | 'double' | 'triple' | 'long' | 'double_then_long' | 'single_then_long' | 'double_then_single', index: number, field: string, value: any) => {
    const newActions = { ...data.actions };
    if (!newActions[actionType]) {
      newActions[actionType] = [];
    }
    
    // When changing action type, clean fields to only keep valid ones for new type
    if (field === 'action') {
      const currentAction = newActions[actionType][index];
      newActions[actionType][index] = cleanActionFields(value, currentAction) as any;
    } else if (field === '__batch') {
      // Batch update: value is an object with multiple fields to set at once
      const current = { ...newActions[actionType][index] };
      for (const [k, v] of Object.entries(value)) {
        if (v === undefined) {
          delete (current as any)[k];
        } else {
          (current as any)[k] = v;
        }
      }
      newActions[actionType][index] = current;
    } else if (field === 'remote_device') {
      // Clear dependent fields when changing remote device
      newActions[actionType][index] = { ...newActions[actionType][index], [field]: value, output_id: undefined, cover_id: undefined, presets: undefined, colors: undefined };
    } else if (field === 'output_id') {
      // Clear presets/colors when changing output
      newActions[actionType][index] = { ...newActions[actionType][index], [field]: value, presets: undefined, colors: undefined };
    } else {
      newActions[actionType][index] = { ...newActions[actionType][index], [field]: value };
    }
    
    console.log('newActions', newActions, data);
    onChange({ ...data, actions: newActions });
  };

  const addAction = (actionType: 'single' | 'double' | 'triple' | 'long' | 'double_then_long' | 'single_then_long' | 'double_then_single') => {
    const newActions = { ...data.actions };
    if (!newActions[actionType]) {
      newActions[actionType] = [];
    }
    newActions[actionType].push({ action: 'output' });
    onChange({ ...data, actions: newActions });
  };

  const removeAction = (actionType: 'single' | 'double' | 'triple' | 'long' | 'double_then_long' | 'single_then_long' | 'double_then_single', index: number) => {
    const newActions = { ...data.actions };
    if (newActions[actionType]) {
      newActions[actionType] = newActions[actionType].filter((_: any, i: number) => i !== index);
    }
    onChange({ ...data, actions: newActions });
  };

  const updateMqttSequence = (sequenceType: 'double_then_long' | 'single_then_long' | 'double_then_single', enabled: boolean) => {
    const newMqttSequences = { ...data.mqtt_sequences };
    newMqttSequences[sequenceType] = enabled;
    onChange({ ...data, mqtt_sequences: newMqttSequences });
  };

  const renderActionFields = (type: 'single' | 'double' | 'triple' | 'long' | 'double_then_long' | 'single_then_long' | 'double_then_single', action: any, index: number) => {
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
      />
    );
  };

  return (
    <div className="space-y-4 py-2">
      {/* Validation Errors - sticky at top */}
      {validationErrors.length > 0 && (
        <div className="alert alert-warning sticky top-0 z-10 shadow-lg">
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
        entityType="event"
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

      {/* DaisyUI Tabs - lifted style with bordered content */}
      <div role="tablist" className="tabs tabs-box">
        <input 
          type="radio" 
          name="event_tabs" 
          role="tab" 
          className="tab" 
          aria-label={t('settings.basic_settings')}
          checked={activeTab === 'basic'}
          onChange={() => setActiveTab('basic')}
        />
        <input 
          type="radio" 
          name="event_tabs" 
          role="tab" 
          className="tab" 
          aria-label={`${t('event_form.single_click')}${data.actions?.single?.length ? ` (${data.actions.single.length})` : ''}`}
          checked={activeTab === 'single'}
          onChange={() => setActiveTab('single')}
        />
        <input 
          type="radio" 
          name="event_tabs" 
          role="tab" 
          className="tab" 
          aria-label={`${t('event_form.double_click')}${data.actions?.double?.length ? ` (${data.actions.double.length})` : ''}`}
          checked={activeTab === 'double'}
          onChange={() => setActiveTab('double')}
        />
        <input 
          type="radio" 
          name="event_tabs" 
          role="tab" 
          className="tab" 
          aria-label={`${t('event_form.triple_click')}${data.actions?.triple?.length ? ` (${data.actions.triple.length})` : ''}`}
          checked={activeTab === 'triple'}
          onChange={() => setActiveTab('triple')}
        />
        <input 
          type="radio" 
          name="event_tabs" 
          role="tab" 
          className="tab" 
          aria-label={`${t('event_form.long_click')}${data.actions?.long?.length ? ` (${data.actions.long.length})` : ''}`}
          checked={activeTab === 'long'}
          onChange={() => setActiveTab('long')}
        />
        <input 
          type="radio" 
          name="event_tabs" 
          role="tab" 
          className="tab" 
          aria-label={`${t('event_form.sequences')}${((data.actions?.double_then_long?.length || 0) + (data.actions?.single_then_long?.length || 0) + (data.actions?.double_then_single?.length || 0)) > 0 ? ` (${(data.actions?.double_then_long?.length || 0) + (data.actions?.single_then_long?.length || 0) + (data.actions?.double_then_single?.length || 0)})` : ''}`}
          checked={activeTab === 'sequences'}
          onChange={() => setActiveTab('sequences')}
        />
        <input 
          type="radio" 
          name="event_tabs" 
          role="tab" 
          className="tab" 
          aria-label={t('settings.advanced_settings')}
          checked={activeTab === 'advanced'}
          onChange={() => setActiveTab('advanced')}
        />
      </div>

      {/* Tab Content with border */}
      <div className="border border-base-300 rounded-b-box rounded-tr-box bg-base-100 p-4">
        {/* Basic Settings Tab */}
        {activeTab === 'basic' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">{t('outputs.display_name')}</span>
                </label>
                <input
                  type="text"
                  className="input w-full"
                  placeholder={t('sensors.event_name_placeholder')}
                  value={data.name || ''}
                  onChange={(e) => updateField('name', e.target.value)}
                />
                <label className="label">
                  <span className="label-text-alt">{t('common.optional')}</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text font-medium">boneIO Input</span>
                </label>
                <Select
                  value={data.boneio_input || ''}
                  onValueChange={(value) => updateField('boneio_input', value)}
                >
                  <SelectTrigger className={`w-full uppercase ${usedInputs.length > 0 && boneioInputOptions.length === 0 ? 'border-warning' : ''}`}>
                    <SelectValue placeholder="Select input..." />
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
                  <span className="label-text font-medium">{t('common.area')}</span>
                </label>
                <Select
                  value={data.area || '_none_'}
                  onValueChange={(value) => updateField('area', value === '_none_' ? undefined : value)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={t('common.no_area')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_none_">{t('common.no_area')}</SelectItem>
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

            </div>
          </div>
        )}

        {/* Single Press Actions Tab */}
        {activeTab === 'single' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">{t('event_form.single_actions')}</h3>
            <button
              onClick={() => addAction('single')}
              className="btn btn-primary btn-sm"
            >
              <FaPlus className="mr-2" />
              {t('inputs.add_action')}
            </button>
          </div>
          
          {data.actions?.single && data.actions.single.length > 0 ? (
            data.actions.single.map((action: any, index: number) => 
              renderActionFields('single', action, index)
            )
          ) : (
            <div className="text-center py-8 text-base-content/60">
              <p>{t('event_form.no_single_actions')}</p>
              <p className="text-sm">{t('event_form.click_add_action')}</p>
            </div>
          )}
        </div>
      )}

        {/* Double Press Actions Tab */}
        {activeTab === 'double' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">{t('event_form.double_actions')}</h3>
            <button
              onClick={() => addAction('double')}
              className="btn btn-primary btn-sm"
            >
              <FaPlus className="mr-2" />
              {t('inputs.add_action')}
            </button>
          </div>
          
          {data.actions?.double && data.actions.double.length > 0 ? (
            data.actions.double.map((action: any, index: number) => 
              renderActionFields('double', action, index)
            )
          ) : (
            <div className="text-center py-8 text-base-content/60">
              <p>{t('event_form.no_double_actions')}</p>
              <p className="text-sm">{t('event_form.click_add_action')}</p>
            </div>
          )}
        </div>
      )}

        {/* Triple Press Actions Tab */}
        {activeTab === 'triple' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">{t('event_form.triple_actions')}</h3>
            <button
              onClick={() => addAction('triple')}
              className="btn btn-primary btn-sm"
            >
              <FaPlus className="mr-2" />
              {t('inputs.add_action')}
            </button>
          </div>
          
          {/* Warning if triple actions exist but enable_triple_click is off */}
          {data.actions?.triple && data.actions.triple.length > 0 && !data.enable_triple_click && (
            <div className="alert alert-warning">
              <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
              <span>{t('event_form.triple_click_disabled_warning')}</span>
            </div>
          )}
          
          {data.actions?.triple && data.actions.triple.length > 0 ? (
            data.actions.triple.map((action: any, index: number) => 
              renderActionFields('triple', action, index)
            )
          ) : (
            <div className="text-center py-8 text-base-content/60">
              <p>{t('event_form.no_triple_actions')}</p>
              <p className="text-sm">{t('event_form.click_add_action')}</p>
            </div>
          )}
        </div>
      )}

        {/* Long Press Actions Tab */}
        {activeTab === 'long' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">{t('event_form.long_actions')}</h3>
            <button
              onClick={() => addAction('long')}
              className="btn btn-primary btn-sm"
            >
              <FaPlus className="mr-2" />
              {t('inputs.add_action')}
            </button>
          </div>
          
          {data.actions?.long && data.actions.long.length > 0 ? (
            data.actions.long.map((action: any, index: number) => 
              renderActionFields('long', action, index)
            )
          ) : (
            <div className="text-center py-8 text-base-content/60">
              <p>{t('event_form.no_long_actions')}</p>
              <p className="text-sm">{t('event_form.click_add_action')}</p>
            </div>
          )}
        </div>
      )}

        {/* Sequences Tab */}
        {activeTab === 'sequences' && (
        <div className="space-y-6">
          <div className="alert alert-info">
            <span>{t('event_form.sequences_hint')}</span>
          </div>

          {/* Double then Long */}
          <div className="card bg-base-200">
            <div className="card-body">
              <div className="flex justify-between items-center">
                <h4 className="card-title text-base">{t('event_form.double_then_long')}</h4>
                <div className="flex items-center gap-2">
                  <label className="label cursor-pointer gap-2">
                    <span className="label-text text-sm">MQTT</span>
                    <input 
                      type="checkbox" 
                      className="checkbox checkbox-sm checkbox-primary"
                      checked={data.mqtt_sequences?.double_then_long || false}
                      onChange={(e) => updateMqttSequence('double_then_long', e.target.checked)}
                    />
                  </label>
                  <button
                    onClick={() => addAction('double_then_long')}
                    className="btn btn-primary btn-sm"
                  >
                    <FaPlus className="mr-2" />
                    {t('inputs.add_action')}
                  </button>
                </div>
              </div>
              <p className="text-sm text-base-content/60">{t('event_form.double_then_long_hint')}</p>
              
              {data.actions?.double_then_long && data.actions.double_then_long.length > 0 ? (
                data.actions.double_then_long.map((action: any, index: number) => 
                  renderActionFields('double_then_long', action, index)
                )
              ) : (
                <div className="text-center py-4 text-base-content/60">
                  <p className="text-sm">{t('event_form.no_actions_configured')}</p>
                </div>
              )}
            </div>
          </div>

          {/* Single then Long */}
          <div className="card bg-base-200">
            <div className="card-body">
              <div className="flex justify-between items-center">
                <h4 className="card-title text-base">{t('event_form.single_then_long')}</h4>
                <div className="flex items-center gap-2">
                  <label className="label cursor-pointer gap-2">
                    <span className="label-text text-sm">MQTT</span>
                    <input 
                      type="checkbox" 
                      className="checkbox checkbox-sm checkbox-primary"
                      checked={data.mqtt_sequences?.single_then_long || false}
                      onChange={(e) => updateMqttSequence('single_then_long', e.target.checked)}
                    />
                  </label>
                  <button
                    onClick={() => addAction('single_then_long')}
                    className="btn btn-primary btn-sm"
                  >
                    <FaPlus className="mr-2" />
                    {t('inputs.add_action')}
                  </button>
                </div>
              </div>
              <p className="text-sm text-base-content/60">{t('event_form.single_then_long_hint')}</p>
              
              {data.actions?.single_then_long && data.actions.single_then_long.length > 0 ? (
                data.actions.single_then_long.map((action: any, index: number) => 
                  renderActionFields('single_then_long', action, index)
                )
              ) : (
                <div className="text-center py-4 text-base-content/60">
                  <p className="text-sm">{t('event_form.no_actions_configured')}</p>
                </div>
              )}
            </div>
          </div>

          {/* Double then Single */}
          <div className="card bg-base-200">
            <div className="card-body">
              <div className="flex justify-between items-center">
                <h4 className="card-title text-base">{t('event_form.double_then_single')}</h4>
                <div className="flex items-center gap-2">
                  <label className="label cursor-pointer gap-2">
                    <span className="label-text text-sm">MQTT</span>
                    <input 
                      type="checkbox" 
                      className="checkbox checkbox-sm checkbox-primary"
                      checked={data.mqtt_sequences?.double_then_single || false}
                      onChange={(e) => updateMqttSequence('double_then_single', e.target.checked)}
                    />
                  </label>
                  <button
                    onClick={() => addAction('double_then_single')}
                    className="btn btn-primary btn-sm"
                  >
                    <FaPlus className="mr-2" />
                    {t('inputs.add_action')}
                  </button>
                </div>
              </div>
              <p className="text-sm text-base-content/60">{t('event_form.double_then_single_hint')}</p>
              
              {data.actions?.double_then_single && data.actions.double_then_single.length > 0 ? (
                data.actions.double_then_single.map((action: any, index: number) => 
                  renderActionFields('double_then_single', action, index)
                )
              ) : (
                <div className="text-center py-4 text-base-content/60">
                  <p className="text-sm">{t('event_form.no_actions_configured')}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

        {/* Advanced Settings Tab */}
        {activeTab === 'advanced' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="form-control">
              <SimpleTimePeriodInput
                label={t('inputs.bounce_time')}
                value={data.bounce_time || '30ms'}
                onChange={(value) => updateField('bounce_time', value)}
                maximum={1000}
                allowedUnits={['ms', 's']}
              />
              <label className="label">
                <span className="label-text-alt">{t('inputs.bounce_time_hint')} ({t('common.default')}: 30ms)</span>
              </label>
            </div>

            <div className="form-control">
              <SimpleTimePeriodInput
                label={t('event_form.double_click_duration')}
                value={data.double_click_duration || '220ms'}
                onChange={(value) => updateField('double_click_duration', value)}
                maximum={2000}
                allowedUnits={['ms', 's']}
              />
              <label className="label">
                <span className="label-text-alt">{t('event_form.double_click_duration_hint')} ({t('common.default')}: 220ms)</span>
              </label>
            </div>

            <div className="form-control">
              <SimpleTimePeriodInput
                label={t('event_form.long_press_duration')}
                value={data.long_press_duration || '400ms'}
                onChange={(value) => updateField('long_press_duration', value)}
                maximum={5000}
                allowedUnits={['ms', 's']}
              />
              <label className="label">
                <span className="label-text-alt">{t('event_form.long_press_duration_hint')} ({t('common.default')}: 400ms)</span>
              </label>
            </div>

            <div className="form-control">
              <SimpleTimePeriodInput
                label={t('event_form.sequence_window_duration')}
                value={data.sequence_window_duration || '500ms'}
                onChange={(value) => updateField('sequence_window_duration', value)}
                maximum={2000}
                allowedUnits={['ms', 's']}
              />
              <label className="label">
                <span className="label-text-alt">{t('event_form.sequence_window_duration_hint')} ({t('common.default')}: 500ms)</span>
              </label>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{t('event_form.sequence_mode')}</span>
              </label>
              <Select
                  value={data.sequence_mode || 'exclusive'}
                  onValueChange={(value) => updateField('sequence_mode', value)}  
                >
                  <SelectTrigger className={`w-full uppercase ${usedInputs.length > 0 && boneioInputOptions.length === 0 ? 'border-warning' : ''}`}>
                    <SelectValue placeholder="Select sequence mode..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="exclusive">{t('event_form.sequence_mode_exclusive')}</SelectItem>
                    <SelectItem value="immediate">{t('event_form.sequence_mode_immediate')}</SelectItem>
                  </SelectContent>
                </Select>
              <label className="label">
                <span className="label-text-alt">
                  {data.sequence_mode === 'exclusive' 
                    ? t('event_form.sequence_mode_exclusive_hint')
                    : t('event_form.sequence_mode_immediate_hint')}
                </span>
              </label>
            </div>

            <div className="form-control">
              <label className="label cursor-pointer justify-start gap-3">
                <input
                  type="checkbox"
                  className="checkbox checkbox-primary"
                  checked={data.enable_triple_click || false}
                  onChange={(e) => updateField('enable_triple_click', e.target.checked)}
                />
                <span className="label-text font-medium">{t('event_form.enable_triple_click')}</span>
              </label>
              <label className="label py-0">
                <span className="label-text-alt">{t('event_form.enable_triple_click_hint')}</span>
              </label>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{t('event_form.long_press_mqtt_mode')}</span>
              </label>
              <Select
                  value={data.long_press_mqtt_mode || 'single'}
                  onValueChange={(value) => updateField('long_press_mqtt_mode', value)}  
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="single">{t('event_form.long_press_mqtt_single')}</SelectItem>
                    <SelectItem value="periodic">{t('event_form.long_press_mqtt_periodic')}</SelectItem>
                  </SelectContent>
                </Select>
              <label className="label">
                <span className="label-text-alt">
                  {data.long_press_mqtt_mode === 'periodic' 
                    ? t('event_form.long_press_mqtt_periodic_hint')
                    : t('event_form.long_press_mqtt_single_hint')}
                </span>
              </label>
            </div>

            <div className="form-control">
              <SimpleTimePeriodInput
                label={t('event_form.max_long_press_duration')}
                value={data.max_long_press_duration || '120s'}
                onChange={(value) => updateField('max_long_press_duration', value)}
                maximum={600000}
                minimum={1000}
                allowedUnits={['s']}
              />
              <label className="label">
                <span className="label-text-alt">{t('event_form.max_long_press_duration_hint')} ({t('common.default')}: 120s)</span>
              </label>
            </div>
          </div>

          {/* Timing validation warning */}
          {(() => {
            const doubleMs = convertTimeperiodToMilliseconds(data.double_click_duration);
            const longMs = convertTimeperiodToMilliseconds(data.long_press_duration);
            if (doubleMs > 0 && longMs > 0 && doubleMs >= longMs) {
              return (
                <div className="alert alert-warning mt-2">
                  <span>{t('event_form.timing_validation_error')}</span>
                </div>
              );
            }
            return null;
          })()}

          <div className="mt-4">
            <button
              type="button"
              className="btn btn-sm btn-outline"
              onClick={() => {
                updateField('bounce_time', '30ms');
                updateField('double_click_duration', '220ms');
                updateField('long_press_duration', '400ms');
                updateField('sequence_window_duration', '500ms');
                updateField('max_long_press_duration', '120s');
              }}
            >
              {t('event_form.restore_defaults')}
            </button>
          </div>
        </div>
      )}
      </div>
    </div>
  );
};

export default EventForm;
