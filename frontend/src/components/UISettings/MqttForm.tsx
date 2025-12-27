import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface MqttFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for MQTT section configuration.
 * Fields: host, username, password, port, topic_prefix, ha_discovery
 */
const MqttForm: React.FC<MqttFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const handleHaDiscoveryChange = (field: string, value: any) => {
    const haDiscovery = data?.ha_discovery || {};
    onChange({
      ...data,
      ha_discovery: { ...haDiscovery, [field]: value }
    });
  };

  return (
    <div className="space-y-4">
      {/* Host */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('mqtt_config.host')} <span className="text-error">*</span></span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.host || ''}
          onChange={(e) => handleChange('host', e.target.value)}
          placeholder="192.168.1.100 or mqtt.local"
          required
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('mqtt_config.host_help')}</span>
        </label>
      </div>

      {/* Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('mqtt_config.port')}</span>
        </label>
        <input
          type="number"
          className="input input-bordered w-full"
          value={data?.port ?? 1883}
          onChange={(e) => handleChange('port', parseInt(e.target.value) || 1883)}
          placeholder="1883"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('mqtt_config.port_help')}</span>
        </label>
      </div>

      {/* Username */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('mqtt_config.username')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.username || ''}
          onChange={(e) => handleChange('username', e.target.value || undefined)}
          placeholder="mqtt_user"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('mqtt_config.username_help')}</span>
        </label>
      </div>

      {/* Password */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('mqtt_config.password')}</span>
        </label>
        <input
          type="password"
          className="input input-bordered w-full"
          value={data?.password || ''}
          onChange={(e) => handleChange('password', e.target.value || undefined)}
          placeholder="••••••••"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('mqtt_config.password_help')}</span>
        </label>
      </div>

      {/* Topic Prefix */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('mqtt_config.topic_prefix')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.topic_prefix || ''}
          onChange={(e) => handleChange('topic_prefix', e.target.value || undefined)}
          placeholder="boneio"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('mqtt_config.topic_prefix_help')}</span>
        </label>
      </div>

      {/* HA Discovery Section */}
      <div className="divider">{t('mqtt_config.ha_discovery')}</div>

      {/* HA Discovery Enabled */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            checked={data?.ha_discovery?.enabled ?? true}
            onChange={(e) => handleHaDiscoveryChange('enabled', e.target.checked)}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('mqtt_config.enable_ha_discovery')}</span>
            <span className="label-text-alt text-base-content/60">{t('mqtt_config.enable_ha_discovery_help')}</span>
          </div>
        </label>
      </div>

      {/* HA Discovery Topic Prefix */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('mqtt_config.ha_discovery_prefix')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.ha_discovery?.topic_prefix || 'homeassistant'}
          onChange={(e) => handleHaDiscoveryChange('topic_prefix', e.target.value || 'homeassistant')}
          placeholder="homeassistant"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">{t('mqtt_config.ha_discovery_prefix_help')}</span>
        </label>
      </div>

      {/* BoneIO Autodiscovery Section */}
      <div className="divider">{t('mqtt_config.boneio_autodiscovery')}</div>

      {/* Send BoneIO Autodiscovery */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            checked={data?.send_boneio_autodiscovery ?? true}
            onChange={(e) => handleChange('send_boneio_autodiscovery', e.target.checked)}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('mqtt_config.send_boneio_autodiscovery')}</span>
            <span className="label-text-alt text-base-content/60">{t('mqtt_config.send_boneio_autodiscovery_help')}</span>
          </div>
        </label>
      </div>

      {/* Receive BoneIO Autodiscovery */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            checked={data?.receive_boneio_autodiscovery ?? true}
            onChange={(e) => handleChange('receive_boneio_autodiscovery', e.target.checked)}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('mqtt_config.receive_boneio_autodiscovery')}</span>
            <span className="label-text-alt text-base-content/60">{t('mqtt_config.receive_boneio_autodiscovery_help')}</span>
          </div>
        </label>
      </div>
    </div>
  );
};

export default MqttForm;
