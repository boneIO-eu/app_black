import React from 'react';

interface BoneIOFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for boneIO section configuration.
 * Fields: name, version, device_type
 */
const BoneIOForm: React.FC<BoneIOFormProps> = ({ data, onChange }) => {
  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  return (
    <div className="space-y-4">
      {/* Name */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Name</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder="BoneIO device name"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Name of boneIO. Default is Black.</span>
        </label>
      </div>

      {/* Version */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Hardware Version</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.version || ''}
          onChange={(e) => handleChange('version', e.target.value || undefined)}
        >
          <option value="">-- Select version --</option>
          <option value="0.7">0.7</option>
          <option value="0.8">0.8</option>
        </select>
        <label className="label">
          <span className="label-text-alt text-base-content/60">BoneIO Black Hardware version</span>
        </label>
      </div>

      {/* Device Type */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Device Type</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.device_type || ''}
          onChange={(e) => handleChange('device_type', e.target.value || undefined)}
        >
          <option value="">-- Select device type --</option>
          <option value="32x10a">32x10A (32 outputs, 10A each)</option>
          <option value="24x16a">24x16A (24 outputs, 16A each)</option>
          <option value="cover">Cover</option>
          <option value="cover mix">Cover Mix</option>
        </select>
        <label className="label">
          <span className="label-text-alt text-base-content/60">Predefined device type configuration</span>
        </label>
      </div>
    </div>
  );
};

export default BoneIOForm;
