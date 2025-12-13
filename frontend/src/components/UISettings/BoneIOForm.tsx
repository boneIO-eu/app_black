import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface BoneIOFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for boneIO section configuration.
 * Fields: name, version, device_type
 */
const BoneIOForm: React.FC<BoneIOFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  // Check if name is required (when version or device_type is set)
  const hasOtherFields = data?.version || data?.device_type;
  const hasName = data?.name && data.name.trim() !== '';
  const nameError = hasOtherFields && !hasName;

  return (
    <div className="space-y-4">
      {/* Name */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">
            {t('boneio_config.name')}
            {hasOtherFields && <span className="text-error ml-1">*</span>}
          </span>
        </label>
        <input
          type="text"
          className={`input input-bordered w-full ${nameError ? 'input-error' : ''}`}
          value={data?.name || ''}
          onChange={(e) => handleChange('name', e.target.value)}
          placeholder={t('boneio_config.name_placeholder')}
        />
        <label className="label">
          {nameError ? (
            <span className="label-text-alt text-error">{t('boneio_config.name_required_error')}</span>
          ) : (
            <span className="label-text-alt text-base-content/60">{t('boneio_config.name_help')}</span>
          )}
        </label>
      </div>

      {/* Version */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('boneio_config.hardware_version')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.version || ''}
          onChange={(e) => handleChange('version', e.target.value || undefined)}
        >
          <option value="">{t('boneio_config.select_version')}</option>
          <option value="0.7">0.7</option>
          <option value="0.8">0.8</option>
        </select>
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('boneio_config.hardware_version_help')}</span>
        </label>
      </div>

      {/* Device Type */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('boneio_config.device_type')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.device_type || ''}
          onChange={(e) => handleChange('device_type', e.target.value || undefined)}
        >
          <option value="">{t('boneio_config.select_device_type')}</option>
          <option value="32x10a">32x10A (32 outputs, 10A each)</option>
          <option value="24x16a">24x16A (24 outputs, 16A each)</option>
          <option value="cover">Cover</option>
          <option value="cover mix">Cover Mix</option>
        </select>
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('boneio_config.device_type_help')}</span>
        </label>
      </div>
    </div>
  );
};

export default BoneIOForm;
