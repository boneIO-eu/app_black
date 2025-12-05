import React, { useState, useMemo } from 'react';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';

interface Area {
  id: string;
  name: string;
}

interface CoverFormProps {
  data: any;
  onChange: (data: any) => void;
  schema?: any;
  allOutputs?: any[];
  allAreas?: Area[];
}

const CoverForm: React.FC<CoverFormProps> = ({ 
  data, 
  onChange, 
  schema,
  allOutputs = [],
  allAreas = []
}) => {
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');

  // Get available outputs that have output_type === 'cover' (or deprecated 'none')
  const availableCoverOutputs = useMemo(() => {
    return allOutputs
      .filter(output => {
        const outputType = output.output_type?.toLowerCase();
        return outputType === 'cover'; // 'none' is deprecated
      })
      .map(output => output.boneio_output || output.id)
      .filter(Boolean);
  }, [allOutputs]);

  // Extract enums from schema
  const platformOptions = schema?.items?.properties?.platform?.enum || ['time_based', 'venetian', 'previous'];
  const deviceClassOptions = schema?.items?.properties?.device_class?.enum || [
    'awning', 'blind', 'curtain', 'damper', 'door', 'garage', 'gate', 'shade', 'shutter', 'window'
  ];

  const updateField = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const selectedPlatform = data.platform || 'previous';
  const showTiltDuration = selectedPlatform === 'venetian';
  const showActuatorDuration = selectedPlatform === 'previous';

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
          {/* Display Name */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Display Name</span>
            </label>
            <input
              type="text"
              className="input w-full"
              value={data.name || ''}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder="e.g., Living Room Blinds"
            />
            <label className="label">
              <span className="label-text-alt text-info">
                Friendly name shown in Home Assistant. If not set, uses ID.
              </span>
            </label>
          </div>

          {/* ID */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">ID</span>
            </label>
            <input
              type="text"
              className="input w-full"
              value={data.id || ''}
              onChange={(e) => updateField('id', e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))}
              placeholder="Auto-generated from relays if empty"
            />
            <label className="label">
              <span className="label-text-alt text-info">
                Technical ID for MQTT topics. Only lowercase letters, numbers and underscores.
                {!data.id && data.open_relay && data.close_relay && (
                  <span className="block mt-1">
                    Will be: <code className="bg-base-300 px-1 rounded">cover_{data.open_relay}_{data.close_relay}</code>
                  </span>
                )}
              </span>
            </label>
          </div>

          {/* Area / Room */}
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
              <span className="label-text-alt whitespace-normal break-words">
                {allAreas.length === 0 
                  ? 'Define areas in the Areas/Rooms section first'
                  : 'Creates sub-device linked to main BoneIO device'
                }
              </span>
            </label>
          </div>

          {/* Platform */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Platform *</span>
            </label>
            <select
              className="select ed w-full"
              value={selectedPlatform}
              onChange={(e) => updateField('platform', e.target.value)}
            >
              {platformOptions.map((platform: string) => (
                <option key={platform} value={platform}>
                  {platform.toUpperCase()}
                </option>
              ))}
            </select>
            <label className="label">
              <span className="label-text-alt text-info">
                {selectedPlatform === 'time_based' && 'Standard time-based cover control'}
                {selectedPlatform === 'venetian' && 'Venetian blinds with tilt support'}
                {selectedPlatform === 'previous' && 'Previous position tracking with actuator'}
              </span>
            </label>
          </div>

          {/* Open Relay */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Open Relay *</span>
            </label>
            {availableCoverOutputs.length === 0 ? (
              <div className="alert alert-warning">
                <span>No cover outputs available. Please configure outputs with output_type='cover' first.</span>
              </div>
            ) : (
              <select
                className="select select-bordered w-full"
                value={data.open_relay || ''}
                onChange={(e) => updateField('open_relay', e.target.value)}
              >
                <option value="">Select open relay...</option>
                {availableCoverOutputs.map((output: string) => (
                  <option 
                    key={output} 
                    value={output} 
                    disabled={output === data.close_relay}
                  >
                    {output} {output === data.close_relay ? '(used as Close Relay)' : ''}
                  </option>
                ))}
              </select>
            )}
            <label className="label">
              <span className="label-text-alt text-info">
                Output used to open the cover
              </span>
            </label>
          </div>

          {/* Close Relay */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Close Relay *</span>
            </label>
            {availableCoverOutputs.length === 0 ? (
              <div className="alert alert-warning">
                <span>No cover outputs available. Please configure outputs with output_type='cover' first.</span>
              </div>
            ) : (
              <select
                className="select select-bordered w-full"
                value={data.close_relay || ''}
                onChange={(e) => updateField('close_relay', e.target.value)}
              >
                <option value="">Select close relay...</option>
                {availableCoverOutputs.map((output: string) => (
                  <option 
                    key={output} 
                    value={output} 
                    disabled={output === data.open_relay}
                  >
                    {output} {output === data.open_relay ? '(used as Open Relay)' : ''}
                  </option>
                ))}
              </select>
            )}
            <label className="label">
              <span className="label-text-alt text-info">
                Output used to close the cover
              </span>
            </label>
          </div>

          {/* Open Time */}
          <SimpleTimePeriodInput
            value={data.open_time || ''}
            onChange={(value: string) => updateField('open_time', value)}
            label="Open Time"
            required={true}
            minimum={1000}
          />

          {/* Close Time */}
          <SimpleTimePeriodInput
            value={data.close_time || ''}
            onChange={(value: string) => updateField('close_time', value)}
            label="Close Time"
            required={true}
            minimum={1000}
          />

          {/* Tilt Duration - only for venetian */}
          {showTiltDuration && (
            <SimpleTimePeriodInput
              value={data.tilt_duration || ''}
              onChange={(value: string) => updateField('tilt_duration', value)}
              label="Tilt Duration"
              required={false}
              minimum={10}
            />
          )}

          {/* Actuator Activation Duration - only for previous */}
          {showActuatorDuration && (
            <SimpleTimePeriodInput
              value={data.actuator_activation_duration || ''}
              onChange={(value: string) => updateField('actuator_activation_duration', value)}
              label="Actuator Activation Duration"
              required={false}
              minimum={0}
            />
          )}
        </div>
      )}

      {/* Advanced Tab */}
      {activeTab === 'advanced' && (
        <div className="space-y-4">
          {/* Device Class */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">Device Class</span>
            </label>
            <select
              className="select ed w-full"
              value={data.device_class || ''}
              onChange={(e) => updateField('device_class', e.target.value || undefined)}
            >
              <option value="">None</option>
              {deviceClassOptions.map((deviceClass: string) => (
                <option key={deviceClass} value={deviceClass}>
                  {deviceClass.toUpperCase()}
                </option>
              ))}
            </select>
            <label className="label">
              <span className="label-text-alt text-info">
                Device class for Home Assistant UI
              </span>
            </label>
          </div>

          {/* Restore State */}
          <div className="form-control">
            <label className="label cursor-pointer justify-start gap-4">
              <input
                type="checkbox"
                className="checkbox"
                checked={data.restore_state || false}
                onChange={(e) => updateField('restore_state', e.target.checked)}
              />
              <div>
                <span className="label-text font-medium">Restore State</span>
                <p className="text-sm text-base-content/70 mt-1">
                  Restore saved state after restart
                </p>
              </div>
            </label>
          </div>

          {/* Show in HA */}
          <div className="form-control">
            <label className="label cursor-pointer justify-start gap-4">
              <input
                type="checkbox"
                className="checkbox"
                checked={data.show_in_ha !== false}
                onChange={(e) => updateField('show_in_ha', e.target.checked)}
              />
              <div>
                <span className="label-text font-medium">Show in Home Assistant</span>
                <p className="text-sm text-base-content/70 mt-1">
                  Enable Home Assistant discovery for this cover
                </p>
              </div>
            </label>
          </div>
        </div>
      )}

    </div>
  );
};

export default CoverForm;
