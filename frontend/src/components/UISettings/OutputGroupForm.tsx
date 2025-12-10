import React, { useState } from 'react';
import { sanitizeId } from './helpers/idValidation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface OutputGroupFormProps {
  data: any;
  onChange: (data: any) => void;
  schema?: any;
  allOutputs?: any[];
  allAreas?: any[];
}

const OutputGroupForm: React.FC<OutputGroupFormProps> = ({ 
  data, 
  onChange, 
  schema,
  allOutputs = [],
  allAreas = []
}) => {
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  // Get available outputs from allOutputs with their names
  // Filter out outputs with output_type 'cover' - they cannot be part of groups
  const availableOutputs = allOutputs
    .filter(output => output.boneio_output && output.output_type !== 'cover')
    .map(output => ({
      id: output.boneio_output,
      name: output.name || output.id || output.boneio_output,
      displayName: `${output.name || output.id || output.boneio_output} : ${output.boneio_output}`,
      outputType: output.output_type
    }))
    .sort((a, b) => a.id.localeCompare(b.id));

  // Extract enums from schema
  const outputTypeOptions = schema?.items?.properties?.output_type?.enum || ['switch', 'light'];

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleOutputsChange = (selectedOutputs: string[]) => {
    updateField('outputs', selectedOutputs);
  };

  const toggleOutput = (outputId: string) => {
    const currentOutputs = Array.isArray(data.outputs) ? data.outputs : [];
    const newOutputs = currentOutputs.includes(outputId)
      ? currentOutputs.filter((o: string) => o !== outputId)
      : [...currentOutputs, outputId];
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
              <span className="label-text font-medium">ID *</span>
            </label>
            <input
              type="text"
              className="input w-full"
              value={data.id || ''}
              onChange={(e) => updateField('id', sanitizeId(e.target.value))}
              placeholder="e.g., lights_living_room"
            />
            <label className="label">
              <span className="label-text-alt text-info">
                Technical identifier used in MQTT topics and actions.
              </span>
            </label>
          </div>

          {/* Name */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Display Name</span>
            </label>
            <input
              type="text"
              className="input w-full"
              value={data.name || ''}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder="e.g., Living Room Lights"
            />
            <label className="label">
              <span className="label-text-alt text-info">
                Optional friendly name shown in Home Assistant. If not set, uses ID.
              </span>
            </label>
          </div>

          {/* Outputs Selection */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Member Outputs *</span>
            </label>
            <div className="border border-base-300 rounded-lg p-3">
              {availableOutputs.length === 0 ? (
                <p className="text-warning">No outputs available. Please configure outputs first.</p>
              ) : (
                <div className="flex flex-col gap-1">
                  {availableOutputs.map((output) => (
                    <label 
                      key={output.id} 
                      className={`label cursor-pointer justify-start gap-3 px-3 py-2 rounded-lg hover:bg-base-200 transition-colors ${
                        selectedOutputs.includes(output.id) ? 'bg-primary/10' : ''
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="checkbox checkbox-sm checkbox-primary"
                        checked={selectedOutputs.includes(output.id)}
                        onChange={() => toggleOutput(output.id)}
                      />
                      <span className="label-text flex-1">
                        <span className="font-medium">{output.name}</span>
                        <span className="text-base-content/60 ml-2 uppercase text-xs">({output.id})</span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
            <div className="flex justify-between mt-2">
              <label className="label py-0">
                <span className="label-text-alt text-info">
                  Selected: {selectedOutputs.length > 0 
                    ? selectedOutputs.map((id: string) => {
                        const output = availableOutputs.find(o => o.id === id);
                        return output ? output.name : id;
                      }).join(', ') 
                    : 'None'}
                </span>
              </label>
              {selectedOutputs.length === 0 && (
                <label className="label py-0">
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
            <Select
              value={data.output_type || 'switch'}
              onValueChange={(value) => updateField('output_type', value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select type..." />
              </SelectTrigger>
              <SelectContent>
                {outputTypeOptions.map((type: string) => (
                  <SelectItem key={type} value={type}>
                    {type.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <label className="label">
              <span className="label-text-alt text-info">
                Device type in Home Assistant (switch or light)
              </span>
            </label>
          </div>

          {/* Area */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Area</span>
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
                {allAreas.map((area: any) => (
                  <SelectItem key={area.id} value={area.id}>
                    {area.name || area.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <label className="label">
              <span className="label-text-alt text-info">
                Assign this group to a specific area/sub-device in Home Assistant
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
