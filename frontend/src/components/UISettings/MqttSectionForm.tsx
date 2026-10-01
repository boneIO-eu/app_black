import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import MqttForm, { type MqttFormData } from './MqttForm';

interface MqttSectionFormProps {
  data: MqttFormData;
  onChange: (data: MqttFormData) => void;
}

/**
 * The `mqtt` section: an "Enabled" switch, then the broker form.
 */
const MqttSectionForm: React.FC<MqttSectionFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const enabled = data?.enabled !== false; // default enabled

  return (
    <div className="space-y-4">
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="toggle toggle-primary"
            checked={enabled}
            onChange={(e) => onChange({ ...data, enabled: e.target.checked })}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('messaging.enable_mqtt')}</span>
            <span className="label-text-alt text-base-content/60">{t('messaging.enable_mqtt_help')}</span>
          </div>
        </label>
      </div>

      {enabled ? (
        <MqttForm data={data} onChange={onChange} />
      ) : (
        <div className="alert">
          <span>{t('messaging.mqtt_disabled_info')}</span>
        </div>
      )}
    </div>
  );
};

export default MqttSectionForm;
