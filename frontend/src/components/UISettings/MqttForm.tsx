import React, { useState } from 'react';
import axiosInstance from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { NumericInput } from '@/components/ui/NumericInput';
import HelpLabel from './components/HelpLabel';

interface MqttFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for MQTT section configuration.
 * Fields: host, username, password, port, ha_discovery
 */
const MqttForm: React.FC<MqttFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const [isRemoving, setIsRemoving] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [removeResult, setRemoveResult] = useState<{ status: string; message: string } | null>(null);
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

  const removeHaDiscovery = async () => {
    if (!confirm(t('mqtt_config.confirm_remove_ha_discovery') || 'Are you sure you want to remove ALL devices from Home Assistant? This action cannot be undone.')) {
      return;
    }
    setIsRemoving(true);
    setRemoveResult(null);
    try {
      const { data: result } = await axiosInstance.post('/api/config/remove_ha_discovery');
      setRemoveResult({ status: 'success', message: result.message });
    } catch (err: any) {
      const msg = err?.response?.data?.detail || t('mqtt_config.remove_ha_discovery_failed') || 'Failed to remove HA discovery entries.';
      setRemoveResult({ status: 'error', message: msg });
    } finally {
      setIsRemoving(false);
    }
  };

  const resendHaDiscovery = async () => {
    if (!confirm(t('mqtt_config.confirm_resend_ha_discovery') || 'Remove and re-send all HA Discovery entries? Devices will be briefly removed and then re-created.')) {
      return;
    }
    setIsResending(true);
    setRemoveResult(null);
    try {
      const { data: result } = await axiosInstance.post('/api/config/resend_ha_discovery');
      setRemoveResult({ status: 'success', message: result.message });
    } catch (err: any) {
      const msg = err?.response?.data?.detail || t('mqtt_config.resend_ha_discovery_failed') || 'Failed to resend HA discovery entries.';
      setRemoveResult({ status: 'error', message: msg });
    } finally {
      setIsResending(false);
    }
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
        <HelpLabel>{t('mqtt_config.host_help')}</HelpLabel>
      </div>

      {/* Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('mqtt_config.port')}</span>
        </label>
        <NumericInput
          value={data?.port ?? 1883}
          onChange={(v) => handleChange('port', v === '' ? 1883 : v)}
          placeholder="1883"
        />
        <HelpLabel>{t('mqtt_config.port_help')}</HelpLabel>
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
        <HelpLabel>{t('mqtt_config.username_help')}</HelpLabel>
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
        <HelpLabel>{t('mqtt_config.password_help')}</HelpLabel>
      </div>

      {/* HA Discovery Section */}
      <div className="divider">{t('mqtt_config.ha_discovery')}</div>

      {/* HA Discovery Enabled */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4 whitespace-normal">
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            checked={data?.ha_discovery?.enabled ?? true}
            onChange={(e) => handleHaDiscoveryChange('enabled', e.target.checked)}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('mqtt_config.enable_ha_discovery')}</span>
            <span className="label-text-alt text-base-content/60 wrap-break-word">{t('mqtt_config.enable_ha_discovery_help')}</span>
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
        <HelpLabel>{t('mqtt_config.ha_discovery_prefix_help')}</HelpLabel>
      </div>

      {/* Remove all HA Discovery entries */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('mqtt_config.remove_ha_discovery')}</span>
        </label>
        <p className="text-sm text-base-content/60 mb-2">
          {t('mqtt_config.remove_ha_discovery_help')}
        </p>
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            className="btn btn-warning btn-sm"
            onClick={resendHaDiscovery}
            disabled={isRemoving || isResending}
          >
            {isResending
              ? <span className="loading loading-spinner loading-xs" />
              : t('mqtt_config.resend_ha_discovery_btn')
            }
          </button>
          <button
            type="button"
            className="btn btn-error btn-sm"
            onClick={removeHaDiscovery}
            disabled={isRemoving || isResending}
          >
            {isRemoving
              ? <span className="loading loading-spinner loading-xs" />
              : t('mqtt_config.remove_ha_discovery_btn')
            }
          </button>
        </div>
        {removeResult && (
          <div className={`alert mt-2 ${removeResult.status === 'success' ? 'alert-success' : 'alert-error'}`}>
            <span>{removeResult.message}</span>
          </div>
        )}
      </div>

      {/* BoneIO Autodiscovery Section */}
      <div className="divider">{t('mqtt_config.boneio_autodiscovery')}</div>

      {/* Send BoneIO Autodiscovery */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4 whitespace-normal">
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            checked={data?.send_boneio_autodiscovery ?? true}
            onChange={(e) => handleChange('send_boneio_autodiscovery', e.target.checked)}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('mqtt_config.send_boneio_autodiscovery')}</span>
            <span className="label-text-alt text-base-content/60 wrap-break-word">{t('mqtt_config.send_boneio_autodiscovery_help')}</span>
          </div>
        </label>
      </div>

      {/* Receive BoneIO Autodiscovery */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4 whitespace-normal">
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            checked={data?.receive_boneio_autodiscovery ?? true}
            onChange={(e) => handleChange('receive_boneio_autodiscovery', e.target.checked)}
          />
          <div className="flex flex-col">
            <span className="label-text font-medium">{t('mqtt_config.receive_boneio_autodiscovery')}</span>
            <span className="label-text-alt text-base-content/60 wrap-break-word">{t('mqtt_config.receive_boneio_autodiscovery_help')}</span>
          </div>
        </label>
      </div>

      {/* Update Section */}
      <div className="divider">{t('mqtt_config.update_settings')}</div>

      {/* Update Channel */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">{t('mqtt_config.update_channel')}</span>
        </label>
        <select
          className="select select-bordered w-full"
          value={data?.update_channel || 'stable'}
          onChange={(e) => handleChange('update_channel', e.target.value)}
        >
          <option value="stable">{t('mqtt_config.update_channel_stable')}</option>
          <option value="dev">{t('mqtt_config.update_channel_dev')}</option>
        </select>
        <HelpLabel>{t('mqtt_config.update_channel_help')}</HelpLabel>
      </div>
    </div>
  );
};

export default MqttForm;
