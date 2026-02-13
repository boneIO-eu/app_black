import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import ThermostatForm from './ThermostatForm';
import AlarmPanelForm from './AlarmPanelForm';
import type { TemplateFormProps } from './types/template';
import { PLATFORM_OPTIONS } from './types/template';

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
}) => {
  const { t } = useTranslation();

  const platform = data.platform || 'thermostat';

  const handlePlatformChange = (value: string) => {
    const newData = { ...data, platform: value };

    // Clean up platform-specific fields when platform changes
    if (value === 'thermostat') {
      delete newData.zones;
      delete newData.outputs;
      delete newData.arming_time;
      delete newData.delay_time;
      delete newData.trigger_time;
      delete newData.code;
      delete newData.code_arm_required;
    } else if (value === 'alarm_control_panel') {
      delete newData.sensor_id;
      delete newData.output_id;
      delete newData.mode;
      delete newData.target_temperature;
      delete newData.hysteresis;
      delete newData.min_temperature;
      delete newData.max_temperature;
    }

    onChange(newData);
  };

  const subFormProps = { data, onChange, allOutputs, allAreas, allSensors, allInputs };

  return (
    <div className="space-y-4">
      {/* Platform selector */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('template.platform')} *</span>
        </label>
        <Select
          value={platform}
          onValueChange={handlePlatformChange}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t('template.select_platform')} />
          </SelectTrigger>
          <SelectContent>
            {PLATFORM_OPTIONS.map((p) => (
              <SelectItem key={p} value={p}>
                {t(`template.platform_${p}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="label">
          <span className="label-text-alt text-info">
            {platform === 'thermostat' && t('template.platform_thermostat_hint')}
            {platform === 'alarm_control_panel' && t('template.platform_alarm_hint')}
          </span>
        </label>
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
