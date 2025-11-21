import React, { useState } from 'react';
import { FaPlus, FaTrash } from 'react-icons/fa';
import Form from '@rjsf/core';
import validator from '@rjsf/validator-ajv8';

interface Action {
  action: string;
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
  id?: string;
  pin?: string;
  boneio_input?: string;
  bounce_time?: string | number;
  show_in_ha?: boolean;
  inverted?: boolean;
  clear_message?: boolean;
  device_class?: string;
  actions?: {
    pressed?: Action[];
    released?: Action[];
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
  allOutputs?: any[];
  allCovers?: any[];
}

const BinarySensorForm: React.FC<BinarySensorFormProps> = ({
  data,
  onChange,
  onSave,
  onCancel,
  isNew,
  schema,
  allBinarySensors = [],
  allEvents = [],
  allOutputs = [],
  allCovers = [],
  editingIndex
}) => {
  const [activeTab, setActiveTab] = useState<'basic' | 'pressed' | 'released'>('basic');

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

  // Predefined schemas for each action type
  const actionSchemas = {
    output: {
      type: 'object',
      required: ['action', 'pin'],
      properties: {
        action: {
          type: 'string',
          enum: actionTypeOptions,
          title: 'Action Type'
        },
        pin: {
          type: 'string',
          title: 'Output',
          enum: allOutputs.map((o: any) => o.id),
          description: 'Select output for this action'
        },
        action_output: {
          type: 'string',
          enum: actionOutputOptions,
          default: 'TOGGLE',
          title: 'Output Action'
        }
      }
    },
    cover: {
      type: 'object',
      required: ['action', 'pin'],
      properties: {
        action: {
          type: 'string',
          enum: actionTypeOptions,
          title: 'Action Type'
        },
        pin: {
          type: 'string',
          title: 'Cover',
          enum: allCovers.map((c: any) => c.id),
          description: 'Select cover for this action'
        },
        action_cover: {
          type: 'string',
          enum: actionCoverOptions,
          default: 'TOGGLE',
          title: 'Cover Action'
        }
      }
    },
    mqtt: {
      type: 'object',
      required: ['action', 'topic'],
      properties: {
        action: {
          type: 'string',
          enum: actionTypeOptions,
          title: 'Action Type'
        },
        topic: {
          type: 'string',
          title: 'MQTT Topic',
          description: 'MQTT topic to publish to'
        },
        action_mqtt_msg: {
          type: 'string',
          title: 'Message',
          description: 'Message to send'
        }
      }
    },
    output_over_mqtt: {
      type: 'object',
      required: ['action', 'pin', 'boneio_id'],
      properties: {
        action: {
          type: 'string',
          enum: actionTypeOptions,
          title: 'Action Type'
        },
        pin: {
          type: 'string',
          title: 'Output',
          enum: allOutputs.map((o: any) => o.id),
          description: 'Select output for this action'
        },
        boneio_id: {
          type: 'string',
          title: 'BoneIO ID',
          description: 'Remote BoneIO device ID'
        }
      }
    },
    cover_over_mqtt: {
      type: 'object',
      required: ['action', 'pin', 'boneio_id'],
      properties: {
        action: {
          type: 'string',
          enum: actionTypeOptions,
          title: 'Action Type'
        },
        pin: {
          type: 'string',
          title: 'Cover',
          enum: allCovers.map((c: any) => c.id),
          description: 'Select cover for this action'
        },
        boneio_id: {
          type: 'string',
          title: 'BoneIO ID',
          description: 'Remote BoneIO device ID'
        }
      }
    }
  };

  // Get schema for action type
  const getActionSchema = (actionType: string): any => {
    const actionTypeLower = actionType.toLowerCase();
    return actionSchemas[actionTypeLower as keyof typeof actionSchemas] || actionSchemas.output;
  };

  // UI schema for action form
  const actionUiSchema = {
    'ui:order': ['action', '*'],
    action: {
      'ui:widget': 'select'
    },
    pin: {
      'ui:widget': 'select',
      'ui:placeholder': 'Select output or cover...'
    },
    action_output: {
      'ui:widget': 'select'
    },
    action_cover: {
      'ui:widget': 'select'
    },
    topic: {
      'ui:placeholder': 'e.g., boneio/input/IN_48'
    },
    boneio_id: {
      'ui:placeholder': 'e.g., boneio_12345'
    }
  };

  const updateAction = (
    type: 'pressed' | 'released',
    index: number,
    field: keyof Action,
    value: any
  ) => {
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
      updatedActions[index] = { ...updatedActions[index], [field]: value };
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
      <div key={index} className="card bg-base-200 p-4 mb-3">
        <div className="flex justify-between items-start mb-3">
          <h4 className="font-semibold">Action {index + 1}</h4>
          <button
            onClick={() => removeAction(type, index)}
            className="btn btn-ghost btn-sm text-error"
          >
            <FaTrash />
          </button>
        </div>

        {/* Use RJSF for action form */}
        <Form
          schema={getActionSchema(action.action || 'output')}
          uiSchema={actionUiSchema}
          formData={action}
          validator={validator}
          onChange={(e) => {
            // Update all fields from RJSF form
            if (e.formData) {
              Object.keys(e.formData).forEach(field => {
                updateAction(type, index, field as keyof Action, (e.formData as any)[field]);
              });
            }
          }}
          className="space-y-4"
        />
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* DaisyUI Tabs */}
      <div className="tabs tabs-border">
        <a 
          className={`tab ${activeTab === 'basic' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('basic')}
        >
          Basic Settings
        </a>
        <a 
          className={`tab ${activeTab === 'pressed' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('pressed')}
        >
          Pressed Actions
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
          Released Actions
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
                <span className="label-text font-medium">ID</span>
              </label>
              <input
                type="text"
                className="input  w-full"
                placeholder="e.g., IN_48"
                value={data.id || ''}
                onChange={(e) => updateField('id', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">ID to use in HA. Default to pin number.</span>
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
                <span className="label-text font-medium">Bounce Time (ms)</span>
              </label>
              <input
                type="number"
                className="input  w-full"
                placeholder="120"
                value={typeof data.bounce_time === 'number' ? data.bounce_time : 120}
                onChange={(e) => updateField('bounce_time', parseInt(e.target.value) || 120)}
              />
              <label className="label">
                <span className="label-text-alt">Debounce time in milliseconds</span>
              </label>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">Device Class</span>
              </label>
              <select
                className="select ed w-full"
                value={data.device_class || ''}
                onChange={(e) => updateField('device_class', e.target.value)}
              >
                <option value="">None</option>
                {deviceClassOptions.map((deviceClass: string) => (
                  <option key={deviceClass} value={deviceClass}>
                    {deviceClass.split('_').map(word => 
                      word.charAt(0).toUpperCase() + word.slice(1)
                    ).join(' ')}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="divider">Options</div>

          <div className="grid grid-cols-1 gap-4">
            <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
              <legend className="fieldset-legend">Show in Home Assistant</legend>
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="toggle toggle-primary"
                  checked={data.show_in_ha !== false}
                  onChange={(e) => updateField('show_in_ha', e.target.checked)}
                />
                <span className="label-text wrap-break-word">If you want you can disable discovering this input in HA</span>
              </label>
            </fieldset>

            <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
              <legend className="fieldset-legend">Inverted</legend>
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="toggle toggle-primary"
                  checked={data.inverted === true}
                  onChange={(e) => updateField('inverted', e.target.checked)}
                />
                <span className="label-text">Check if sensor type is inverted.</span>
              </label>
            </fieldset>

            <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
              <legend className="fieldset-legend">Clear Message</legend>
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="toggle toggle-primary"
                  checked={data.clear_message === true}
                  onChange={(e) => updateField('clear_message', e.target.checked)}
                />
                <span className="label-text">Clear message after processing</span>
              </label>
            </fieldset>
          </div>
        </div>
      )}

      {/* Pressed Actions Tab */}
      {activeTab === 'pressed' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">Pressed Actions</h3>
            <button
              type="button"
              onClick={() => addAction('pressed')}
              className="btn btn-primary btn-sm"
            >
              <FaPlus className="mr-2" />
              Add Action
            </button>
          </div>

          {data.actions?.pressed && data.actions.pressed.length > 0 ? (
            data.actions.pressed.map((action, index) =>
              renderActionFields(action, 'pressed', index)
            )
          ) : (
            <div className="text-center py-8 text-base-content/60">
              <p>No pressed actions configured</p>
              <p className="text-sm">Click "Add Action" to create one</p>
            </div>
          )}
        </div>
      )}

      {/* Released Actions Tab */}
      {activeTab === 'released' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">Released Actions</h3>
            <button
              type="button"
              onClick={() => addAction('released')}
              className="btn btn-primary btn-sm"
            >
              <FaPlus className="mr-2" />
              Add Action
            </button>
          </div>

          {data.actions?.released && data.actions.released.length > 0 ? (
            data.actions.released.map((action, index) =>
              renderActionFields(action, 'released', index)
            )
          ) : (
            <div className="text-center py-8 text-base-content/60">
              <p>No released actions configured</p>
              <p className="text-sm">Click "Add Action" to create one</p>
            </div>
          )}
        </div>
      )}

    </div>
  );
};

export default BinarySensorForm;
