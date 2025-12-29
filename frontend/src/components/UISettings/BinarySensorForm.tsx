import React, { useState } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import { sanitizeId } from './helpers/idValidation';
import { normalizeCovers } from './helpers/coverUtils';
import { useTranslation } from '@/hooks/useTranslation';
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
  allOutputs?: any[];
  allOutputGroups?: any[];
  allCovers?: any[];
  allAreas?: Area[];
  onValidationChange?: (hasErrors: boolean) => void;
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
  editingIndex,
  onValidationChange,
  savedOutputs,
  savedOutputGroups,
  savedCovers
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'basic' | 'pressed' | 'released'>('basic');

  /**
   * Check if an output is saved (committed) by comparing with saved data.
   */
  const isOutputSaved = (outputId: string): boolean => {
    if (!savedOutputs) return true;
    return savedOutputs.some((o: any) => {
      const id = o.id || o.boneio_output;
      return id === outputId;
    });
  };

  const isOutputGroupSaved = (groupId: string): boolean => {
    if (!savedOutputGroups) return true;
    return savedOutputGroups.some((g: any) => g.id === groupId);
  };

  const isCoverSaved = (coverId: string): boolean => {
    if (!savedCovers) return true;
    const normalized = normalizeCovers(savedCovers);
    return normalized.some(c => c.id === coverId);
  };

  // Validate action - check if required fields are filled
  const validateAction = (action: Action): string | null => {
    if (!action.action) return t('binary_sensor_form.action_type_required');
    
    const actionType = action.action.toLowerCase();
    
    if (actionType === 'output' || actionType === 'output_over_mqtt') {
      if (!action.boneio_output) return t('binary_sensor_form.output_required_for_output_actions');
    }
    
    if (actionType === 'cover' || actionType === 'cover_over_mqtt') {
      if (!action.boneio_cover) return t('binary_sensor_form.cover_required_for_cover_actions');
    }
    
    if (actionType === 'mqtt') {
      if (!action.topic) return t('binary_sensor_form.topic_required_for_mqtt_actions');
    }
    
    if (actionType === 'output_over_mqtt' || actionType === 'cover_over_mqtt') {
      if (!action.boneio_id) return t('binary_sensor_form.boneio_id_required_for_remote_actions');
    }
    
    return null;
  };

  // Get all validation errors
  const getValidationErrors = (): string[] => {
    const errors: string[] = [];
    
    ['pressed', 'released'].forEach((type) => {
      const actions = data.actions?.[type as 'pressed' | 'released'] || [];
      actions.forEach((action: Action, index: number) => {
        const error = validateAction(action);
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
    'mqtt', 'output', 'cover', 'output_over_mqtt', 'cover_over_mqtt'
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
    const actionType = action.action || 'output';

    return (
      <div key={index} className="border border-base-300 rounded-lg p-4 mb-4">
        <div className="flex justify-between items-center mb-3">
          <h4 className="font-medium">{t('binary_sensor_form.action')} {index + 1}</h4>
          <button
            onClick={() => removeAction(type, index)}
            className="btn btn-ghost btn-xs text-error"
          >
            <FaTrash />
          </button>
        </div>

        <div className="form-control mb-3">
          <label className="label">
            <span className="label-text font-medium">{t('binary_sensor_form.action_type')}</span>
          </label>
          <Select
            value={actionType}
            onValueChange={(value) => updateAction(type, index, 'action', value)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('binary_sensor_form.select_action')} />
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

        {actionType === 'cover' && (
          <>
            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.cover')}</span>
              </label>
              <Select
                value={action.boneio_cover || action.pin || ''}
                onValueChange={(value) => updateAction(type, index, 'boneio_cover', value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('binary_sensor_form.select_cover')} />
                </SelectTrigger>
                <SelectContent>
                  {normalizeCovers(allCovers).map((cover) => {
                      const name = cover.name || cover.id;
                      const label = name !== cover.id ? `${name} (${cover.id})` : cover.id;
                      const isSaved = isCoverSaved(cover.id);
                      return (
                        <SelectItem 
                          key={cover.id} 
                          value={cover.id}
                          disabled={!isSaved}
                          className={!isSaved ? 'opacity-50 cursor-not-allowed' : ''}
                        >
                          {!isSaved && <span className="badge badge-xs badge-warning mr-1">{t('binary_sensor_form.unsaved')}</span>}
                          {label}
                        </SelectItem>
                      );
                    })}
                </SelectContent>
              </Select>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.cover_action')}</span>
              </label>
              <Select
                value={action.action_cover || 'TOGGLE'}
                onValueChange={(value) => updateAction(type, index, 'action_cover', value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('binary_sensor_form.select_action')} />
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
        )}

        {actionType === 'output' && (
          <>
            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.output')}</span>
              </label>
              <Select
                value={action.boneio_output || action.pin || ''}
                onValueChange={(value) => updateAction(type, index, 'boneio_output', value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('binary_sensor_form.select_output')} />
                </SelectTrigger>
                <SelectContent>
                  {/* Regular outputs */}
                  {allOutputs
                    .filter((output: any) => output && typeof output === 'object' && (output.id || output.boneio_output))
                    .map((output: any) => {
                      const id = output.id || output.boneio_output;
                      const name = output.name || id;
                      const label = name !== id ? `${name} (${id})` : id;
                      const isSaved = isOutputSaved(id);
                      return (
                        <SelectItem 
                          key={id} 
                          value={id}
                          disabled={!isSaved}
                          className={!isSaved ? 'opacity-50 cursor-not-allowed' : ''}
                        >
                          {!isSaved && <span className="badge badge-xs badge-warning mr-1">{t('binary_sensor_form.unsaved')}</span>}
                          {label}
                        </SelectItem>
                      );
                    })}
                  {/* Output groups */}
                  {allOutputGroups
                    .filter((group: any) => group && typeof group === 'object' && group.id)
                    .map((group: any) => {
                      const id = group.id;
                      const name = group.name || id;
                      const label = name !== id ? `${name} (${id})` : id;
                      const isSaved = isOutputGroupSaved(id);
                      return (
                        <SelectItem 
                          key={`group-${id}`} 
                          value={id}
                          disabled={!isSaved}
                          className={!isSaved ? 'opacity-50 cursor-not-allowed' : ''}
                        >
                          <span className="badge badge-xs badge-secondary mr-1">{t('binary_sensor_form.group')}</span>
                          {!isSaved && <span className="badge badge-xs badge-warning mr-1">{t('binary_sensor_form.unsaved')}</span>}
                          {label}
                        </SelectItem>
                      );
                    })}
                </SelectContent>
              </Select>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.output_action')}</span>
              </label>
              <Select
                value={action.action_output || 'TOGGLE'}
                onValueChange={(value) => updateAction(type, index, 'action_output', value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('binary_sensor_form.select_action')} />
                </SelectTrigger>
                <SelectContent>
                  {actionOutputOptions.map((option: string) => (
                    <SelectItem key={option} value={option}>
                      {option.charAt(0) + option.slice(1).toLowerCase()}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </>
        )}

        {actionType === 'mqtt' && (
          <>
            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.mqtt_topic')}</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder={t('binary_sensor_form.mqtt_topic_placeholder')}
                value={action.topic || ''}
                onChange={(e) => updateAction(type, index, 'topic', e.target.value)}
              />
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.mqtt_message')}</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder={t('binary_sensor_form.mqtt_message_placeholder')}
                value={action.action_mqtt_msg || ''}
                onChange={(e) => updateAction(type, index, 'action_mqtt_msg', e.target.value)}
              />
            </div>
          </>
        )}

        {actionType === 'output_over_mqtt' && (
          <>
            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">BoneIO ID</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder="e.g., boneio_12345"
                value={action.boneio_id || ''}
                onChange={(e) => updateAction(type, index, 'boneio_id', sanitizeId(e.target.value))}
              />
              <label className="label">
                <span className="label-text-alt">ID of the remote BoneIO device. Auto-sanitized.</span>
              </label>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.output_id')}</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder={t('binary_sensor_form.output_id_placeholder')}
                value={action.pin || ''}
                onChange={(e) => updateAction(type, index, 'pin', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">{t('binary_sensor_form.output_id_hint')}</span>
              </label>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.output_action')}</span>
              </label>
              <Select
                value={action.action_output || 'TOGGLE'}
                onValueChange={(value) => updateAction(type, index, 'action_output', value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('binary_sensor_form.select_action')} />
                </SelectTrigger>
                <SelectContent>
                  {actionOutputOptions.map((option: string) => (
                    <SelectItem key={option} value={option}>
                      {option.charAt(0) + option.slice(1).toLowerCase()}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </>
        )}

        {actionType === 'cover_over_mqtt' && (
          <>
            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">BoneIO ID</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder="e.g., boneio_12345"
                value={action.boneio_id || ''}
                onChange={(e) => updateAction(type, index, 'boneio_id', sanitizeId(e.target.value))}
              />
              <label className="label">
                <span className="label-text-alt">ID of the remote BoneIO device. Auto-sanitized.</span>
              </label>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.cover_id_pin')}</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder={t('binary_sensor_form.cover_id_placeholder')}
                value={action.pin || ''}
                onChange={(e) => updateAction(type, index, 'pin', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">{t('binary_sensor_form.cover_id_hint')}</span>
              </label>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">{t('binary_sensor_form.cover_action')}</span>
              </label>
              <Select
                value={action.action_cover || 'TOGGLE'}
                onValueChange={(value) => updateAction(type, index, 'action_cover', value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('binary_sensor_form.select_action')} />
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
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Validation Errors - sticky at top */}
      {validationErrors.length > 0 && (
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
      <div className="tabs tabs-border">
        <a 
          className={`tab ${activeTab === 'basic' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('basic')}
        >
          {t('settings.basic_settings')}
        </a>
        <a 
          className={`tab ${activeTab === 'pressed' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('pressed')}
        >
          {t('inputs.pressed_actions')}
          {data.actions?.pressed && data.actions.pressed.length > 0 && (
            <span className="badge badge-sm badge-primary ml-2">
              {data.actions.pressed.length}
            </span>
          )}
        </a>
        <a 
          className={`tab ${activeTab === 'released' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('released')}
        >
          {t('inputs.released_actions')}
          {data.actions?.released && data.actions.released.length > 0 && (
            <span className="badge badge-sm badge-primary ml-2">
              {data.actions.released.length}
            </span>
          )}
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
                className="input  w-full"
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
      )}

      {/* Pressed Actions Tab */}
      {activeTab === 'pressed' && (
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
      )}

      {/* Released Actions Tab */}
      {activeTab === 'released' && (
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
      )}

    </div>
  );
};

export default BinarySensorForm;
