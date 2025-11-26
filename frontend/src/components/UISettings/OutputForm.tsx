import React, { useState } from 'react';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';

interface OutputFormProps {
  data: any;
  onChange: (data: any) => void;
  onSave: () => void;
  onCancel: () => void;
  isNew: boolean;
  schema?: any;
  uiSchema?: any;
  deviceType?: string;
  allOutputs?: any[];
  editingIndex?: number | null;
}

const OutputForm: React.FC<OutputFormProps> = ({ 
  data, 
  onChange, 
  schema,
  uiSchema,
  deviceType,
  allOutputs = [],
  editingIndex
}) => {
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  // Extract enums from schema for dropdowns
  const getOutputCount = (deviceType: string) => {
    const type = deviceType?.toLowerCase() || '';
    if (type.includes('32') || type.includes('cm')) {
      return 32; // 32x10A, Cover, Cover Mix
    } else if (type.includes('24')) {
      return 24; // 24x16A
    }
    return 49; // default fallback
  };

  const outputCount = getOutputCount(deviceType || '');
  const allBoneioOutputs = Array.from({ length: outputCount }, (_, i) => i + 1).map(num => `OUT_${num.toString().padStart(2, '0')}`);
  
  // Filter out already used outputs (except current one)
  const usedOutputs = allOutputs
    .filter((output, index) => {
      // Skip current item being edited
      if (editingIndex !== null && index === editingIndex) {
        return false;
      }
      // For new items, just filter out any used outputs
      return output.boneio_output && output !== data;
    })
    .map(output => output.boneio_output);
  
  const availableOutputs = allBoneioOutputs.filter(output => !usedOutputs.includes(output));
  
  // If current output is used by this item, include it in options
  const currentOutput = data.boneio_output;
  const boneioOutputOptions = currentOutput && usedOutputs.includes(currentOutput)
    ? [...new Set([currentOutput, ...availableOutputs])].sort()
    : availableOutputs;
  
  const outputTypeOptions = schema?.items?.properties?.output_type?.enum || [];

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const toggleRestoreState = () => {
    updateField('restore_state', !data.restore_state);
  };


  const getFieldDescription = (fieldName: string) => {
    return uiSchema?.[fieldName]?.['ui:description'] || '';
  };

  const getFieldTitle = (fieldName: string) => {
    return uiSchema?.[fieldName]?.['ui:title'] || fieldName.charAt(0).toUpperCase() + fieldName.slice(1);
  };

  return (
    <div className="space-y-4">
      {/* DaisyUI Tabs */}
      <div className="tabs tabs-bordered tabs-lifted">
        <a 
          className={`tab ${activeTab === 'basic' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('basic')}
        >
          Basic Settings
        </a>
        <a 
          className={`tab ${activeTab === 'advanced' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('advanced')}
        >
          Advanced Settings
        </a>
      </div>

      {/* Basic Settings Tab */}
      {activeTab === 'basic' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{getFieldTitle('id')}</span>
              </label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder="e.g., living_room_light"
                value={data.id || ''}
                onChange={(e) => updateField('id', e.target.value)}
              />
              <label className="label">
                <span className="label-text-alt">{getFieldDescription('id')}</span>
              </label>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{getFieldTitle('boneio_output')}</span>
              </label>
              <select
                className={`select select-bordered w-full uppercase ${usedOutputs.length > 0 && boneioOutputOptions.length === 0 ? 'select-warning' : ''}`}
                value={data.boneio_output || ''}
                onChange={(e) => updateField('boneio_output', e.target.value)}
              >
                <option value="">Select output...</option>
                {boneioOutputOptions.map((output: string) => (
                  <option key={output} value={output}>
                    {output}
                  </option>
                ))}
              </select>
              <label className="label">
                <span className="label-text-alt">{getFieldDescription('boneio_output')}</span>
              </label>
              {usedOutputs.length > 0 && boneioOutputOptions.length === 1 && (
                <label className="label max-w-full">
                  <span 
                    className="label-text-alt text-warning" 
                    style={{ 
                      wordWrap: 'break-word', 
                      wordBreak: 'break-all', 
                      whiteSpace: 'normal',
                      maxWidth: '100%'
                    }}
                  >
                    All outputs are in use. Free one or choose different device type.
                  </span>
                </label>
              )}
              {usedOutputs.length > 0 && (
                <label className="label max-w-full">
                  <span className="label-text-alt text-info whitespace-normal break-all">
                    Used: {usedOutputs.length > 5 
                      ? `${usedOutputs.slice(0, 3).join(', ')}, ... (+${usedOutputs.length - 3} more)`
                      : usedOutputs.join(', ')
                    }
                  </span>
                </label>
              )}
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text font-medium">{getFieldTitle('output_type')}</span>
              </label>
              <select
                className="select select-bordered w-full"
                value={data.output_type || 'none'}
                onChange={(e) => updateField('output_type', e.target.value)}
              >
                {outputTypeOptions.map((type: string) => (
                  <option key={type} value={type}>
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </option>
                ))}
              </select>
              <label className="label">
                <span className="label-text-alt">{getFieldDescription('output_type')}</span>
              </label>
            </div>
          </div>

          <div className="divider">Options</div>

          <div className="grid grid-cols-1 gap-4">
            <fieldset className="fieldset bg-base-100 border-base-300 rounded-box border p-4">
              <legend className="fieldset-legend">{getFieldTitle('restore_state')}</legend>
              <label className="label cursor-pointer justify-start gap-4">
                <input
                  type="checkbox"
                  className="toggle toggle-primary"
                  checked={data.restore_state === true}
                  onChange={toggleRestoreState}
                />
                <span className="label-text">{getFieldDescription('restore_state')}</span>
              </label>
            </fieldset>
          </div>
        </div>
      )}

      {/* Advanced Settings Tab */}
      {activeTab === 'advanced' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Momentary Turn On */}
            <SimpleTimePeriodInput
              value={data.momentary_turn_on || 0}
              onChange={(value: number) => updateField('momentary_turn_on', value || undefined)}
              label={getFieldTitle('momentary_turn_on') || 'Momentary Turn On'}
              required={false}
              minimum={0}
            />

            {/* Momentary Turn Off */}
            <SimpleTimePeriodInput
              value={data.momentary_turn_off || 0}
              onChange={(value: number) => updateField('momentary_turn_off', value || undefined)}
              label={getFieldTitle('momentary_turn_off') || 'Momentary Turn Off'}
              required={false}
              minimum={0}
            />
          </div>

          <div className="alert alert-info">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <div>
              <h3 className="font-bold">Momentary Actions</h3>
              <div className="text-sm">
                <p>When enabled, the output will automatically turn off after the specified duration.</p>
                <p>Useful for buttons, triggers, or pulse-controlled devices.</p>
                <p>Supported time formats: 5s (seconds), 50ms (milliseconds), 2minutes, 1h (hours)</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default OutputForm;
