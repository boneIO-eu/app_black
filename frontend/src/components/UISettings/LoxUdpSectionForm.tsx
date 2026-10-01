import React, { useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import LoxForm, { type LoxFormData } from './LoxForm';

interface LoxUdpSectionFormProps {
  data: LoxFormData;
  onChange: (data: LoxFormData) => void;
  onValidationChange?: (isValid: boolean) => void;
}

/**
 * The `lox_udp` section: an "Enabled" switch, then the Loxone UDP form.
 * Off by default; switching it off makes the section valid without a host.
 */
const LoxUdpSectionForm: React.FC<LoxUdpSectionFormProps> = ({ data, onChange, onValidationChange }) => {
  const { t } = useTranslation();
  const enabled = data?.enabled === true; // default disabled

  const handleEnabledChange = (next: boolean) => {
    if (next) {
      onChange({ enabled: true, ...(data || {}) });
    } else {
      onChange({ ...data, enabled: false });
      onValidationChange?.(true);
    }
  };

  const handleValidation = useCallback((isValid: boolean) => {
    onValidationChange?.(isValid);
  }, [onValidationChange]);

  return (
    <div className="space-y-4">
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="toggle toggle-primary"
            checked={enabled}
            onChange={(e) => handleEnabledChange(e.target.checked)}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('messaging.enable_lox')}</span>
            <span className="label-text-alt text-base-content/60">{t('messaging.enable_lox_help')}</span>
          </div>
        </label>
      </div>

      {enabled ? (
        <LoxForm data={data} onChange={onChange} onValidationChange={handleValidation} />
      ) : (
        <div className="alert">
          <span>{t('messaging.lox_disabled_info')}</span>
        </div>
      )}
    </div>
  );
};

export default LoxUdpSectionForm;
