import React, { useState, useEffect } from 'react';
import axios from '@/api/axios';
import { useTranslation } from '@/hooks/useTranslation';
import { FormInputSelect, FormInputText, FormInputToggle } from './widgets';

interface CANFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for CAN bus section configuration.
 * Fields: enabled, channel, bitrate, node_id, mode, auto_setup, restart_on_error
 */
const CANForm: React.FC<CANFormProps> = ({ data, onChange }) => {
  const { t } = useTranslation();
  const [canInterfaces, setCanInterfaces] = useState<string[]>([]);

  useEffect(() => {
    axios.get('/api/can/interfaces')
      .then(({ data: res }) => setCanInterfaces(res.interfaces || []))
      .catch(() => setCanInterfaces([]));
  }, []);

  const handleChange = (field: string, value: any) => {
    onChange({ ...data, [field]: value });
  };

  const enabled = data?.enabled ?? false;

  return (
    <div className="space-y-4">
      {/* Enabled */}
      <FormInputToggle
        label={t('can_config.enabled')}
        checked={enabled}
        onChange={(checked) => handleChange('enabled', checked)}
        help={t('can_config.enabled_help')}
      />

      {enabled && (
        <>
          {/* Channel */}
          <FormInputSelect
            label={t('can_config.channel')}
            value={data?.channel || 'can0'}
            onChange={(value) => handleChange('channel', value)}
            options={canInterfaces.map((iface) => ({ value: iface, label: iface }))}
            placeholder={canInterfaces.length === 0 ? t('can_config.no_interfaces') : undefined}
            help={t('can_config.channel_help')}
          />

          {/* Bitrate */}
          <FormInputSelect
            label={t('can_config.bitrate')}
            value={data?.bitrate ?? 125000}
            onChange={(value) => handleChange('bitrate', Number(value))}
            options={[
              { value: 10000, label: '10 kbps' },
              { value: 20000, label: '20 kbps' },
              { value: 50000, label: '50 kbps' },
              { value: 100000, label: '100 kbps' },
              { value: 125000, label: '125 kbps (default)' },
              { value: 250000, label: '250 kbps' },
              { value: 500000, label: '500 kbps' },
              { value: 1000000, label: '1 Mbps' },
            ]}
            help={t('can_config.bitrate_help')}
          />

          {/* Node ID */}
          <FormInputText
            label={t('can_config.node_id')}
            value={String(data?.node_id ?? 'auto')}
            onChange={(val) => {
              const num = parseInt(val, 10);
              if (!isNaN(num) && num >= 1 && num <= 127) {
                handleChange('node_id', num);
                return;
              }
              handleChange('node_id', val);
            }}
            placeholder="auto"
            help={t('can_config.node_id_help')}
          />

          {/* Mode */}
          <FormInputSelect
            label={t('can_config.mode')}
            value={data?.mode || 'master'}
            onChange={(value) => handleChange('mode', value)}
            options={[
              { value: 'master', label: t('can_config.mode_master') },
              { value: 'slave', label: t('can_config.mode_slave') },
            ]}
            help={t('can_config.mode_help')}
          />

          {/* Auto-setup */}
          <FormInputToggle
            label={t('can_config.auto_setup')}
            checked={data?.auto_setup ?? true}
            onChange={(checked) => handleChange('auto_setup', checked)}
            help={t('can_config.auto_setup_help')}
          />

          {/* Restart on error */}
          <FormInputToggle
            label={t('can_config.restart_on_error')}
            checked={data?.restart_on_error ?? true}
            onChange={(checked) => handleChange('restart_on_error', checked)}
            help={t('can_config.restart_on_error_help')}
          />
        </>
      )}
    </div>
  );
};

export default CANForm;
