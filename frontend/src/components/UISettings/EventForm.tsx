import React, { useState } from 'react';
import { FaPlus } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import ActionFields, { validateAction } from './ActionFields';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';
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
  BinarySensorEntity 
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
  editingIndex,
  onValidationChange,
  attemptedSubmit = false,
  savedOutputs,
  savedOutputGroups,
  savedCovers
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'single' | 'double' | 'long' | 'advanced'>('basic');

  // Extract enums from schema for dropdowns
  const allBoneioInputs = schema?.items?.properties?.boneio_input?.enum || [];
  
  // Filter out already used inputs from both binary_sensor and event (except current one)
  const usedInputsFromEvents = allEvents
    .filter((event, index) => {
      // Skip current item being edited
      if (editingIndex !== null && index === editingIndex) {
        return false;
      }
      // For new items, just filter out any used inputs
      return event.boneio_input && event !== data;
    })
    .map(event => event.boneio_input);
  
  const usedInputsFromBinarySensors = allBinarySensors
    .filter(sensor => sensor.boneio_input)
    .map(sensor => sensor.boneio_input);
  
  const usedInputs = [...new Set([...usedInputsFromEvents, ...usedInputsFromBinarySensors])];
  
  const availableInputs = allBoneioInputs.filter((input: string) => !usedInputs.includes(input));
  
  // If current input is used by this item, include it in options
  const currentInput = data.boneio_input;
  const boneioInputOptions = currentInput && !availableInputs.includes(currentInput)
    ? [...new Set([currentInput, ...availableInputs])].sort()
    : availableInputs;
  const actionTypeOptions = schema?.items?.properties?.actions?.properties?.single?.items?.properties?.action?.enum || [];
  const actionCoverOptions = schema?.items?.properties?.actions?.properties?.single?.items?.properties?.action_cover?.enum || [];
  const actionOutputOptions = schema?.items?.properties?.actions?.properties?.single?.items?.properties?.action_output?.enum || [];

  const updateField = (field: string, value: any) => {
    console.log('updateField', field, value, data);
    onChange({ ...data, [field]: value });
  };

  // Validate action using imported function

  // Get all validation errors
  const getValidationErrors = (): string[] => {
    const errors: string[] = [];
    
    ['single', 'double', 'long'].forEach((type) => {
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

  const updateAction = (actionType: 'single' | 'double' | 'long', index: number, field: string, value: any) => {
    const newActions = { ...data.actions };
    if (!newActions[actionType]) {
      newActions[actionType] = [];
    }
    
    // When changing action type, clear pin field to avoid mismatched values
    if (field === 'action') {
      const currentAction = newActions[actionType][index];
      newActions[actionType][index] = { 
        action: value,
        // Keep only fields that are common across all action types
        ...(currentAction?.boneio_id && { boneio_id: currentAction.boneio_id })
      };
    } else {
      newActions[actionType][index] = { ...newActions[actionType][index], [field]: value };
    }
    
    console.log('newActions', newActions, data);
    onChange({ ...data, actions: newActions });
  };

  const addAction = (actionType: 'single' | 'double' | 'long') => {
    const newActions = { ...data.actions };
    if (!newActions[actionType]) {
      newActions[actionType] = [];
    }
    newActions[actionType].push({ action: 'output' });
    onChange({ ...data, actions: newActions });
  };

  const removeAction = (actionType: 'single' | 'double' | 'long', index: number) => {
    const newActions = { ...data.actions };
    if (newActions[actionType]) {
      newActions[actionType] = newActions[actionType].filter((_: any, i: number) => i !== index);
    }
    onChange({ ...data, actions: newActions });
  };

  const renderActionFields = (type: 'single' | 'double' | 'long', action: any, index: number) => {
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

      {/* DaisyUI Tabs */}
      <div className="tabs tabs-bordered tabs-lifted">
        <a 
          className={`tab ${activeTab === 'basic' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('basic')}
        >
          {t('settings.basic_settings')}
        </a>
        <a 
          className={`tab ${activeTab === 'single' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('single')}
        >
          {t('event_form.single_click')}
          {data.actions?.single && data.actions.single.length > 0 && (
            <span className="badge badge-sm badge-primary ml-2">
              {data.actions.single.length}
            </span>
          )}
        </a>
        <a 
          className={`tab ${activeTab === 'double' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('double')}
        >
          {t('event_form.double_click')}
          {data.actions?.double && data.actions.double.length > 0 && (
            <span className="badge badge-sm badge-primary ml-2">
              {data.actions.double.length}
            </span>
          )}
        </a>
        <a 
          className={`tab ${activeTab === 'long' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('long')}
        >
          {t('event_form.long_click')}
          {data.actions?.long && data.actions.long.length > 0 && (
            <span className="badge badge-sm badge-primary ml-2">
              {data.actions.long.length}
            </span>
          )}
        </a>
        <a 
          className={`tab ${activeTab === 'advanced' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('advanced')}
        >
          {t('settings.advanced_settings')}
        </a>
      </div>

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
                <span className="label-text font-medium">BoneIO Input</span>
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
                <span className="label-text font-medium">Area / Room</span>
              </label>
              <Select
                value={data.area || '_none_'}
                onValueChange={(value) => updateField('area', value === '_none_' ? undefined : value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="No area (main device)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none_">No area (main device)</SelectItem>
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
                    ? 'Define areas in the Areas/Rooms section first'
                    : 'Creates sub-device linked to main BoneIO device'
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
          </div>

          {/* Timing validation warning */}
          {(() => {
            const parseMs = (val: string | number | undefined, defaultVal: number): number => {
              if (val === undefined) return defaultVal;
              if (typeof val === 'number') return val;
              const match = val.match(/^(\d+(?:\.\d+)?)(ms|s)?$/);
              if (!match) return defaultVal;
              const num = parseFloat(match[1]);
              const unit = match[2] || 'ms';
              return unit === 's' ? num * 1000 : num;
            };
            const doubleMs = parseMs(data.double_click_duration, 220);
            const longMs = parseMs(data.long_press_duration, 400);
            if (doubleMs >= longMs) {
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
              }}
            >
              {t('event_form.restore_defaults')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default EventForm;
