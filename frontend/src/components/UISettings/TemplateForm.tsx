import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import ThermostatForm from './ThermostatForm';
import AlarmPanelForm from './AlarmPanelForm';
import GateCoverForm from './GateCoverForm';
import IrrigationForm from './IrrigationForm';
import type { TemplateFormProps } from './types/template';

const PLATFORM_ICONS: Record<string, string> = {
  thermostat: '🌡️',
  alarm_control_panel: '🚨',
  gate_cover: '🚪',
  irrigation: '💧',
};

/**
 * TemplateForm — platform selector wrapper that delegates to the
 * appropriate sub-form (ThermostatForm, AlarmPanelForm, or GateCoverForm).
 */
const TemplateForm: React.FC<TemplateFormProps> = ({
  data,
  onChange,
  allOutputs = [],
  allAreas = [],
  allSensors = [],
  allInputs = [],
  allRemoteInputs = [],
  allModbusDevices = [],
  onValidationChange,
}) => {
  const { t } = useTranslation();

  const platform = data.platform || 'thermostat';

  const subFormProps = { data, onChange, allOutputs, allAreas, allSensors, allInputs, allRemoteInputs, allModbusDevices, onValidationChange };

  return (
    <div className="space-y-4 mt-2">
      {/* Platform — read-only badge (platform is chosen in the picker dialog) */}
      <div className="flex items-center gap-2">
        <span className="badge badge-lg badge-primary">
          {PLATFORM_ICONS[platform] || '⚙️'} {t(`template.platform_${platform}`)}
        </span>
      </div>

      {/* Platform-specific form */}
      {platform === 'thermostat' ? (
        <ThermostatForm {...subFormProps} />
      ) : platform === 'gate_cover' ? (
        <GateCoverForm {...subFormProps} />
      ) : platform === 'irrigation' ? (
        <IrrigationForm {...subFormProps} />
      ) : (
        <AlarmPanelForm {...subFormProps} />
      )}
    </div>
  );
};

export default TemplateForm;
