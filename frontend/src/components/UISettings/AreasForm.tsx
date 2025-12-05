import React from 'react';

interface AreasFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for Areas item editing.
 * Fields: id, name
 */
const AreasForm: React.FC<AreasFormProps> = ({ data, onChange }) => {
  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  return (
    <div className="space-y-4">
      {/* ID */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Area ID <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.id || ''}
          onChange={(e) => handleChange('id', e.target.value)}
          placeholder="living_room"
          required
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Unique identifier for the area (used in configurations)</span>
        </label>
      </div>

      {/* Name */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Area Name <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder="Living Room"
          required
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Display name shown in Home Assistant</span>
        </label>
      </div>
    </div>
  );
};

export default AreasForm;
