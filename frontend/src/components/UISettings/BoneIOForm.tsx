import React, { useState, useCallback } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { FaExclamationTriangle } from 'react-icons/fa';
import HelpLabel from './components/HelpLabel';

interface ExampleFile {
  filename: string;
  category: string;
  path: string;
}

interface ValidationResult {
  compatible: boolean;
  incompatible_outputs: Array<{ boneio_output: string; id: string; name: string }>;
  incompatible_inputs: Array<{ boneio_input: string; id: string; section: string }>;
  available_example_files: ExampleFile[];
  new_device_type: string;
  normalized_type: string;
}

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
  const [showWarningModal, setShowWarningModal] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [pendingDeviceType, setPendingDeviceType] = useState<string | null>(null);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [resetResult, setResetResult] = useState<any>(null);

  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const validateDeviceTypeChange = useCallback(async (newDeviceType: string) => {
    if (!newDeviceType || newDeviceType === data?.device_type) {
      handleChange('device_type', newDeviceType || undefined);
      return;
    }

    setIsLoading(true);
    try {
      const { data: result } = await axios.post<ValidationResult>('/api/config/validate_device_type_change', {
        new_device_type: newDeviceType,
        version: data?.version || '0.8',
      });

      if (result.compatible) {
        // No conflicts, apply change directly
        handleChange('device_type', newDeviceType);
      } else {
        // Show warning modal
        setValidationResult(result);
        setPendingDeviceType(newDeviceType);
        // Pre-select categories that have example files
        const categories = [...new Set(result.available_example_files.map(f => f.category))];
        const relevantCategories = categories.filter(c => 
          ['output', 'event', 'binary_sensor', 'cover'].includes(c)
        );
        setSelectedCategories(relevantCategories);
        setShowWarningModal(true);
      }
    } catch (error) {
      console.error('Failed to validate device type change:', error);
      // On error, allow the change but warn user
      handleChange('device_type', newDeviceType);
    } finally {
      setIsLoading(false);
    }
  }, [data, handleChange]);

  const handleCancelChange = () => {
    setShowWarningModal(false);
    setValidationResult(null);
    setPendingDeviceType(null);
    setSelectedCategories([]);
    setResetResult(null);
  };

  const handleApplyWithExampleConfig = async () => {
    if (!pendingDeviceType || selectedCategories.length === 0) return;

    setIsLoading(true);
    try {
      const { data: result } = await axios.post('/api/factory_reset/partial', {
        device_type: pendingDeviceType,
        files_to_replace: selectedCategories,
      });
      setResetResult(result);

      if (result.status === 'success') {
        // Apply device type change
        handleChange('device_type', pendingDeviceType);
        // Show success, user needs to restart
      }
    } catch (error) {
      console.error('Failed to apply example config:', error);
      setResetResult({ status: 'error', message: String(error) });
    } finally {
      setIsLoading(false);
    }
  };

  const toggleCategory = (category: string) => {
    setSelectedCategories(prev =>
      prev.includes(category)
        ? prev.filter(c => c !== category)
        : [...prev, category]
    );
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
        {nameError ? (
          <label className="label whitespace-normal"><span className="label-text-alt text-error wrap-break-word">{t('boneio_config.name_required_error')}</span></label>
        ) : (
          <HelpLabel>{t('boneio_config.name_help')}</HelpLabel>
        )}
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
          <option value="0.2">0.2</option>
          <option value="0.3">0.3</option>
          <option value="0.4">0.4</option>
          <option value="0.5">0.5</option>
          <option value="0.6">0.6</option>
          <option value="0.7">0.7</option>
          <option value="0.8">0.8</option>
        </select>
        <HelpLabel>{t('boneio_config.hardware_version_help')}</HelpLabel>
      </div>

      {/* Device Type */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('boneio_config.device_type')}</span>
        </label>
        <div className="relative">
          <select
            className="select select-bordered w-full"
            value={(data?.device_type || '').toLowerCase()}
            onChange={(e) => validateDeviceTypeChange(e.target.value)}
            disabled={isLoading}
          >
            <option value="">{t('boneio_config.select_device_type')}</option>
            <option value="32x10a">32x10A (32 outputs, 10A each)</option>
            <option value="32x5a">32x5A (32 outputs, 5A each)</option>
            <option value="24x16a">24x16A (24 outputs, 16A each)</option>
            <option value="cover">Cover</option>
            <option value="cover mix">Cover Mix</option>
          </select>
          {isLoading && (
            <span className="absolute right-10 top-1/2 -translate-y-1/2 loading loading-spinner loading-sm"></span>
          )}
        </div>
        <HelpLabel>{t('boneio_config.device_type_help')}</HelpLabel>
      </div>

      {/* HA Child Devices (experimental) */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-3">
          <input
            type="checkbox"
            className="toggle toggle-warning"
            checked={data?.ha_child_devices || false}
            onChange={(e) => handleChange('ha_child_devices', e.target.checked)}
          />
          <span className="label-text font-medium">
            {t('boneio_config.ha_child_devices')}
          </span>
        </label>
        <HelpLabel>{t('boneio_config.ha_child_devices_help')}</HelpLabel>
      </div>

      {/* Device Type Change Warning Modal */}
      {showWarningModal && validationResult && (
        <div className="modal modal-open">
          <div className="modal-box max-w-2xl">
            <h3 className="font-bold text-lg flex items-center gap-2">
              <FaExclamationTriangle className="text-warning" />
              {t('boneio_config.device_type_change_warning_title')}
            </h3>
            
            <div className="py-4 space-y-4">
              <p className="text-sm">
                {t('boneio_config.device_type_change_warning_desc')}
              </p>

              {/* Incompatible outputs */}
              {validationResult.incompatible_outputs.length > 0 && (
                <div className="alert alert-warning">
                  <div>
                    <p className="font-semibold">{t('boneio_config.incompatible_outputs')}:</p>
                    <ul className="list-disc list-inside text-sm mt-1">
                      {validationResult.incompatible_outputs.map((out, idx) => (
                        <li key={idx}>
                          <code>{out.boneio_output}</code> ({out.name})
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Incompatible inputs */}
              {validationResult.incompatible_inputs.length > 0 && (
                <div className="alert alert-warning">
                  <div>
                    <p className="font-semibold">{t('boneio_config.incompatible_inputs')}:</p>
                    <ul className="list-disc list-inside text-sm mt-1">
                      {validationResult.incompatible_inputs.map((inp, idx) => (
                        <li key={idx}>
                          <code>{inp.boneio_input}</code> ({inp.section})
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Example config option */}
              <div className="divider">{t('boneio_config.load_example_config')}</div>
              
              <p className="text-sm">
                {t('boneio_config.select_files_to_replace')}
              </p>

              <div className="flex flex-wrap gap-2">
                {['output', 'event', 'binary_sensor', 'cover'].map(category => {
                  const hasFile = validationResult.available_example_files.some(
                    f => f.category === category
                  );
                  if (!hasFile) return null;
                  return (
                    <label key={category} className="label cursor-pointer gap-2">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-primary"
                        checked={selectedCategories.includes(category)}
                        onChange={() => toggleCategory(category)}
                      />
                      <span className="label-text">{category}.yaml</span>
                    </label>
                  );
                })}
              </div>

              {/* Reset result */}
              {resetResult && (
                <div className={`alert ${resetResult.status === 'success' ? 'alert-success' : 'alert-error'}`}>
                  <div>
                    <p>{resetResult.message}</p>
                    {resetResult.status === 'success' && (
                      <p className="text-sm mt-1">
                        {t('boneio_config.restart_required')}
                      </p>
                    )}
                    {resetResult.copied_files && (
                      <p className="text-sm mt-1">
                        {t('boneio_config.copied_files')}: {resetResult.copied_files.join(', ')}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="modal-action">
              <button
                className="btn"
                onClick={handleCancelChange}
                disabled={isLoading}
              >
                {t('common.cancel')}
              </button>
              <button
                className="btn btn-primary"
                onClick={handleApplyWithExampleConfig}
                disabled={isLoading || selectedCategories.length === 0}
              >
                {isLoading ? (
                  <span className="loading loading-spinner loading-sm"></span>
                ) : (
                  t('boneio_config.load_and_apply')
                )}
              </button>
            </div>
          </div>
          <div className="modal-backdrop" onClick={handleCancelChange}></div>
        </div>
      )}
    </div>
  );
};

export default BoneIOForm;
