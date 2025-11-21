import React, { useState } from 'react';

interface OutputGroupFormProps {
  data: any;
  onChange: (data: any) => void;
  schema?: any;
  allOutputs?: any[];
}

const OutputGroupForm: React.FC<OutputGroupFormProps> = ({ 
  data, 
  onChange, 
  schema,
  allOutputs = []
}) => {
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  // Get available outputs from allOutputs
  const availableOutputs = allOutputs
    .filter(output => output.boneio_output)
    .map(output => output.boneio_output);

  // Extract enums from schema
  const outputTypeOptions = schema?.items?.properties?.output_type?.enum || ['switch', 'light'];

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleOutputsChange = (selectedOutputs: string[]) => {
    updateField('outputs', selectedOutputs);
  };

  const toggleOutput = (output: string) => {
    const currentOutputs = Array.isArray(data.outputs) ? data.outputs : [];
    const newOutputs = currentOutputs.includes(output)
      ? currentOutputs.filter((o: string) => o !== output)
      : [...currentOutputs, output];
    handleOutputsChange(newOutputs);
  };

  const selectedOutputs = Array.isArray(data.outputs) ? data.outputs : [];

  return (
    <div className="space-y-4">
      {/* Tabs */}
      <div className="tabs tabs-boxed">
        <button 
          className={`tab ${activeTab === 'basic' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('basic')}
        >
          Basic
        </button>
        <button 
          className={`tab ${activeTab === 'advanced' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('advanced')}
        >
          Advanced
        </button>
      </div>

      {/* Basic Tab */}
      {activeTab === 'basic' && (
        <div className="space-y-4">
          {/* ID */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">ID</span>
            </label>
            <input
              type="text"
              className="input  w-full"
              value={data.id || ''}
              onChange={(e) => updateField('id', e.target.value)}
              placeholder="Optional ID for Home Assistant"
            />
            <label className="label">
              <span className="label-text-alt text-info">
                Optional. If not set, will be auto-generated.
              </span>
            </label>
          </div>

          {/* Outputs Selection */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Outputs *</span>
            </label>
            <div className="border border-base-300 rounded-lg p-4 max-h-64 overflow-y-auto">
              {availableOutputs.length === 0 ? (
                <p className="text-warning">No outputs available. Please configure outputs first.</p>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {availableOutputs.map((output: string) => (
                    <label key={output} className="label cursor-pointer justify-start gap-2">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-sm"
                        checked={selectedOutputs.includes(output)}
                        onChange={() => toggleOutput(output)}
                      />
                      <span className="label-text uppercase">{output}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
            <div className="flex justify-between">
            <label className="label">
              <span className="label-text-alt text-info">
                Selected: {selectedOutputs.length > 0 ? selectedOutputs.join(', ') : 'None'}
              </span>
            </label>
            {selectedOutputs.length === 0 && (
              <label className="label">
                <span className="label-text-alt text-error">
                  At least one output is required
                </span>
              </label>
            )}
            </div>
          </div>

          {/* Output Type */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Output Type</span>
            </label>
            <select
              className="select ed w-full"
              value={data.output_type || 'switch'}
              onChange={(e) => updateField('output_type', e.target.value)}
            >
              {outputTypeOptions.map((type: string) => (
                <option key={type} value={type}>
                  {type.toUpperCase()}
                </option>
              ))}
            </select>
            <label className="label">
              <span className="label-text-alt text-info">
                Device type in Home Assistant (switch or light)
              </span>
            </label>
          </div>
        </div>
      )}

      {/* Advanced Tab */}
      {activeTab === 'advanced' && (
        <div className="space-y-4">
          {/* All On Behaviour */}
          <div className="form-control">
            <label className="label cursor-pointer justify-start gap-4">
              <input
                type="checkbox"
                className="checkbox"
                checked={data.all_on_behaviour || false}
                onChange={(e) => updateField('all_on_behaviour', e.target.checked)}
              />
              <div>
                <span className="label-text font-medium">All On Behaviour</span>
                <p className="text-sm text-base-content/70 mt-1">
                  If true, toggle when all outputs are on. Otherwise, group is on if any output is on.
                </p>
              </div>
            </label>
          </div>
        </div>
      )}

    </div>
  );
};

export default OutputGroupForm;
