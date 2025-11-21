import React, { useState, useMemo } from 'react';
import SimpleTimePeriodInput from './widgets/SimpleTimePeriodInput';

interface CoverFormProps {
  data: any;
  onChange: (data: any) => void;
  schema?: any;
  allOutputs?: any[];
}

const CoverForm: React.FC<CoverFormProps> = ({ 
  data, 
  onChange, 
  schema,
  allOutputs = []
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
          {/* ID */}
          <div className="form-control">
            <label className="label">
              <span className="label-text font-medium">ID *</span>
            </label>
            <input
              type="text"
              className="input  w-full"
              value={data.id || ''}
              onChange={(e) => updateField('id', e.target.value)}
              placeholder="e.g., cover_living_room"
            />
            <label className="label">
              <span className="label-text-alt text-info">
                Unique identifier for Home Assistant
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
                className="select ed w-full"
                value={data.open_relay || ''}
                onChange={(e) => updateField('open_relay', e.target.value)}
              >
                <option value="">Select open relay...</option>
                {availableCoverOutputs.map((output: string) => (
                  <option key={output} value={output} className="uppercase">
                    {output}
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
                className="select ed w-full"
                value={data.close_relay || ''}
                onChange={(e) => updateField('close_relay', e.target.value)}
              >
                <option value="">Select close relay...</option>
                {availableCoverOutputs.map((output: string) => (
                  <option key={output} value={output} className="uppercase">
                    {output}
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
            value={data.open_time || 0}
            onChange={(value: number) => updateField('open_time', value)}
            label="Open Time"
            required={true}
            minimum={1000}
          />

          {/* Close Time */}
          <SimpleTimePeriodInput
            value={data.close_time || 0}
            onChange={(value: number) => updateField('close_time', value)}
            label="Close Time"
            required={true}
            minimum={1000}
          />

          {/* Tilt Duration - only for venetian */}
          {showTiltDuration && (
            <SimpleTimePeriodInput
              value={data.tilt_duration || 0}
              onChange={(value: number) => updateField('tilt_duration', value)}
              label="Tilt Duration"
              required={false}
              minimum={10}
            />
          )}

          {/* Actuator Activation Duration - only for previous */}
          {showActuatorDuration && (
            <SimpleTimePeriodInput
              value={data.actuator_activation_duration || 0}
              onChange={(value: number) => updateField('actuator_activation_duration', value)}
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
