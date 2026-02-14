import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import ThermostatForm from './ThermostatForm';
import AlarmPanelForm from './AlarmPanelForm';
import type { TemplateFormProps } from './types/template';

/**
 * TemplateForm — platform selector wrapper that delegates to the
 * appropriate sub-form (ThermostatForm or AlarmPanelForm).
 */
const TemplateForm: React.FC<TemplateFormProps> = ({
  data,
  onChange,
  allOutputs = [],
  allAreas = [],
  allSensors = [],
  allInputs = [],
  allModbusDevices = [],
}) => {
  const { t } = useTranslation();

  const platform = data.platform || 'thermostat';

  const subFormProps = { data, onChange, allOutputs, allAreas, allSensors, allInputs, allModbusDevices };

  return (
    <div className="space-y-4 mt-2">
      {/* Platform — read-only badge (platform is chosen in the picker dialog) */}
      <div className="flex items-center gap-2">
        <span className="badge badge-lg badge-primary">
          {platform === 'thermostat' ? '🌡️' : '🚨'} {t(`template.platform_${platform}`)}
        </span>
      </div>

      {/* Platform-specific form */}
      {platform === 'thermostat' ? (
        <ThermostatForm {...subFormProps} />
      ) : (
        <AlarmPanelForm {...subFormProps} />
      )}
    </div>
  );
};

export default TemplateForm;
