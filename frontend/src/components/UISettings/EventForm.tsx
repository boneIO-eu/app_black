import React, { useState } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';

interface Area {
  id: string;
  name: string;
}

interface EventFormProps {
  data: any;
  onChange: (data: any) => void;
  onSave: () => void;
  onCancel: () => void;
  isNew: boolean;
  schema?: any;
  allBinarySensors?: any[];
  allEvents?: any[];
  editingIndex?: number | null;
  allOutputs?: any[];
  allCovers?: any[];
  allAreas?: Area[];
  onValidationChange?: (hasErrors: boolean) => void;
}

const EventForm: React.FC<EventFormProps> = ({ 
  data, 
  onChange, 
  schema,
  allBinarySensors = [],
  allEvents = [],
  allOutputs = [],
  allCovers = [],
  allAreas = [],
  editingIndex,
  onValidationChange
}) => {
  const [activeTab, setActiveTab] = useState<'basic' | 'single' | 'double' | 'long'>('basic');

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
    onChange({ ...data, [field]: value });
  };

  // Validate action - check if required fields are filled
  const validateAction = (action: any): string | null => {
    if (!action.action) return 'Action type is required';
    
    const actionType = action.action.toLowerCase();
    
    if (actionType === 'output' || actionType === 'output_over_mqtt') {
      if (!action.pin) return 'Output is required for output actions';
    }
    
    if (actionType === 'cover' || actionType === 'cover_over_mqtt') {
      if (!action.pin) return 'Cover is required for cover actions';
    }
    
    if (actionType === 'mqtt') {
      if (!action.topic) return 'Topic is required for MQTT actions';
    }
    
    if (actionType === 'output_over_mqtt' || actionType === 'cover_over_mqtt') {
      if (!action.boneio_id) return 'BoneIO ID is required for remote actions';
    }
    
    return null;
  };

  // Get all validation errors
  const getValidationErrors = (): string[] => {
    const errors: string[] = [];
    
    ['single', 'double', 'long'].forEach((type) => {
      const actions = data.actions?.[type] || [];
      actions.forEach((action: any, index: number) => {
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
    
    onChange({ ...data, actions: newActions });
  };

  const addAction = (actionType: 'single' | 'double' | 'long') => {
    const newActions = { ...data.actions };
    if (!newActions[actionType]) {
      newActions[actionType] = [];
    }
    newActions[actionType].push({ action: 'mqtt' });
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
    const actionType = action.action || 'mqtt';

    return (
      <div key={index} className="border border-base-300 rounded-lg p-4 mb-4">
        <div className="flex justify-between items-center mb-3">
          <h4 className="font-medium">Action {index + 1}</h4>
          <button
            onClick={() => removeAction(type, index)}
            className="btn btn-ghost btn-xs text-error"
          >
            <FaTrash />
          </button>
        </div>

        <div className="form-control mb-3">
          <label className="label">
            <span className="label-text font-medium">Action Type</span>
          </label>
          <select
            className="select ed w-full"
            value={actionType}
            onChange={(e) => updateAction(type, index, 'action', e.target.value)}
          >
            {actionTypeOptions.map((actionType: string) => (
              <option key={actionType} value={actionType}>
                {actionType.split('_').map(word =>
                  word.charAt(0).toUpperCase() + word.slice(1)
                ).join(' ')}
              </option>
            ))}
          </select>
        </div>

        {(actionType === 'cover' || actionType === 'cover_over_mqtt') && (
          <>
            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">Cover</span>
              </label>
              <select
                className="select select-bordered w-full"
                value={action.pin || ''}
                onChange={(e) => updateAction(type, index, 'pin', e.target.value)}
              >
                <option value="">Select cover...</option>
                {allCovers
                  .filter((cover: any) => cover && typeof cover === 'object' && cover.id)
                  .map((cover: any) => {
                    const id = cover.id;
                    const name = cover.name || id;
                    const label = name !== id ? `${name} - ${id}` : id;
                    return (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    );
                  })}
              </select>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">Cover Action</span>
              </label>
              <select
                className="select ed w-full"
                value={action.action_cover || 'TOGGLE'}
                onChange={(e) => updateAction(type, index, 'action_cover', e.target.value)}
              >
                {actionCoverOptions.map((option: string) => (
                  <option key={option} value={option}>
                    {option.split('_').map(word => 
                      word.charAt(0) + word.slice(1).toLowerCase()
                    ).join(' ')}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        {actionType === 'output' && (
          <>
            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">Output</span>
              </label>
              <select
                className="select select-bordered w-full"
                value={action.pin || ''}
                onChange={(e) => updateAction(type, index, 'pin', e.target.value)}
              >
                <option value="">Select output...</option>
                {allOutputs
                  .filter((output: any) => output && typeof output === 'object' && (output.id || output.boneio_output))
                  .map((output: any) => {
                    const id = output.id || output.boneio_output;
                    const name = output.name || id;
                    const label = name !== id ? `${name} - ${id}` : id;
                    return (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    );
                  })}
              </select>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">Action Output</span>
              </label>
              <select
                className="select ed w-full"
                value={action.action_output || 'TOGGLE'}
                onChange={(e) => updateAction(type, index, 'action_output', e.target.value)}
              >
                {actionOutputOptions.map((option: string) => (
                  <option key={option} value={option}>
                    {option.charAt(0) + option.slice(1).toLowerCase()}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        {actionType === 'mqtt' && (
          <>
            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">MQTT Topic</span>
              </label>
              <input
                type="text"
                className="input  w-full"
                placeholder="e.g., boneio/input/IN_48"
                value={action.topic || ''}
                onChange={(e) => updateAction(type, index, 'topic', e.target.value)}
              />
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">MQTT Message</span>
              </label>
              <input
                type="text"
                className="input  w-full"
                placeholder="Message to send"
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
                className="input  w-full"
                placeholder="e.g., boneio_12345"
                value={action.boneio_id || ''}
                onChange={(e) => updateAction(type, index, 'boneio_id', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">ID of the remote BoneIO device</span>
              </label>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">Output Number (pin)</span>
              </label>
              <input
                type="text"
                className="input  w-full"
                placeholder="e.g., light_kitchen or OUT_01"
                value={action.pin || ''}
                onChange={(e) => updateAction(type, index, 'pin', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">Output ID on the remote BoneIO device</span>
              </label>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">Action Output</span>
              </label>
              <select
                className="select ed w-full"
                value={action.action_output || 'TOGGLE'}
                onChange={(e) => updateAction(type, index, 'action_output', e.target.value)}
              >
                {actionOutputOptions.map((option: string) => (
                  <option key={option} value={option}>
                    {option.charAt(0) + option.slice(1).toLowerCase()}
                  </option>
                ))}
              </select>
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
                className="input  w-full"
                placeholder="e.g., boneio_12345"
                value={action.boneio_id || ''}
                onChange={(e) => updateAction(type, index, 'boneio_id', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">ID of the remote BoneIO device</span>
              </label>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">Cover ID (pin)</span>
              </label>
              <input
                type="text"
                className="input  w-full"
                placeholder="e.g., cover_living_room"
                value={action.pin || ''}
                onChange={(e) => updateAction(type, index, 'pin', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">Cover ID on the remote BoneIO device</span>
              </label>
            </div>

            <div className="form-control mb-3">
              <label className="label">
                <span className="label-text font-medium">Cover Action</span>
              </label>
              <select
                className="select ed w-full"
                value={action.action_cover || 'TOGGLE'}
                onChange={(e) => updateAction(type, index, 'action_cover', e.target.value)}
              >
                {actionCoverOptions.map((option: string) => (
                  <option key={option} value={option}>
                    {option.split('_').map(word => 
                      word.charAt(0) + word.slice(1).toLowerCase()
                    ).join(' ')}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Validation Errors */}
      {validationErrors.length > 0 && (
        <div className="alert alert-error">
          <div>
            <h3 className="font-bold">Validation Errors:</h3>
            <ul className="list-disc list-inside">
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
          Basic Settings
        </a>
        <a 
          className={`tab ${activeTab === 'single' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('single')}
        >
          Single Press
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
          Double Press
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
          Long Press
          {data.actions?.long && data.actions.long.length > 0 && (
            <span className="badge badge-sm badge-primary ml-2">
              {data.actions.long.length}
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
                <span className="label-text font-medium">Name</span>
              </label>
              <input
                type="text"
                className="input w-full"
                placeholder="e.g., Kitchen Button"
                value={data.name || ''}
                onChange={(e) => updateField('name', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">Optional display name for HA</span>
              </label>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">BoneIO Input</span>
              </label>
              <select
                className={`select ed w-full uppercase ${usedInputs.length > 0 && boneioInputOptions.length === 0 ? 'select-warning' : ''}`}
                value={data.boneio_input || ''}
                onChange={(e) => updateField('boneio_input', e.target.value)}
              >
                <option value="">Select input...</option>
                {boneioInputOptions.map((input: string) => (
                  <option key={input} value={input}>
                    {input}
                  </option>
                ))}
              </select>
              {usedInputs.length > 0 && boneioInputOptions.length === 1 && (
                <label className="label max-w-full">
                  <span className="label-text-alt text-warning whitespace-normal break-all">
                    All inputs are in use. You have to free one first.
                  </span>
                </label>
              )}
              {usedInputs.length > 0 && (
                <label className="label max-w-full">
                  <span className="label-text-alt text-info whitespace-normal break-all">
                    Used: {usedInputs.length > 5 
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
              <select
                className="select select-bordered w-full"
                value={data.area || ''}
                onChange={(e) => updateField('area', e.target.value || undefined)}
              >
                <option value="">No area (main device)</option>
                {allAreas.map((area) => (
                  <option key={area.id} value={area.id}>
                    {area.name}
                  </option>
                ))}
              </select>
              <label className="label">
                <span className="label-text-alt">
                  {allAreas.length === 0 
                    ? 'Define areas in the Areas/Rooms section first'
                    : 'Creates sub-device linked to main BoneIO device'
                  }
                </span>
              </label>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">Bounce Time</span>
              </label>
              <input
                type="text"
                className="input  w-full"
                placeholder="e.g., 30ms"
                value={data.bounce_time || '30ms'}
                onChange={(e) => updateField('bounce_time', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">Bounce time for GPIO in milliseconds</span>
              </label>
            </div>
          </div>

          <div className="divider">Options</div>

          <div className="grid grid-cols-1 gap-4">
            <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
              <legend className="fieldset-legend">Clear Message</legend>
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="toggle toggle-primary"
                  checked={data.clear_message === true}
                  onChange={(e) => updateField('clear_message', e.target.checked)}
                />
                <span className="label-text">Decide if after press/release callback send empty message to mqtt. Same as Zigbee2Mqtt is doing in button actions.</span>
              </label>
            </fieldset>
          </div>
        </div>
      )}

      {/* Single Press Actions Tab */}
      {activeTab === 'single' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">Single Press Actions</h3>
            <button
              onClick={() => addAction('single')}
              className="btn btn-primary btn-sm"
            >
              <FaPlus className="mr-2" />
              Add Action
            </button>
          </div>
          
          {data.actions?.single?.map((action: any, index: number) => 
            renderActionFields('single', action, index)
          ) || (
            <div className="text-center py-8 text-base-content/60">
              <p>No single press actions configured</p>
              <p className="text-sm">Click "Add Action" to create your first action</p>
            </div>
          )}
        </div>
      )}

      {/* Double Press Actions Tab */}
      {activeTab === 'double' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">Double Press Actions</h3>
            <button
              onClick={() => addAction('double')}
              className="btn btn-primary btn-sm"
            >
              <FaPlus className="mr-2" />
              Add Action
            </button>
          </div>
          
          {data.actions?.double?.map((action: any, index: number) => 
            renderActionFields('double', action, index)
          ) || (
            <div className="text-center py-8 text-base-content/60">
              <p>No double press actions configured</p>
              <p className="text-sm">Click "Add Action" to create your first action</p>
            </div>
          )}
        </div>
      )}

      {/* Long Press Actions Tab */}
      {activeTab === 'long' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">Long Press Actions</h3>
            <button
              onClick={() => addAction('long')}
              className="btn btn-primary btn-sm"
            >
              <FaPlus className="mr-2" />
              Add Action
            </button>
          </div>
          
          {data.actions?.long?.map((action: any, index: number) => 
            renderActionFields('long', action, index)
          ) || (
            <div className="text-center py-8 text-base-content/60">
              <p>No long press actions configured</p>
              <p className="text-sm">Click "Add Action" to create your first action</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default EventForm;
