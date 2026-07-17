import React, { useState, useCallback } from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { TabsBox } from '@/components/ui/tabs-box';
import MqttForm from './MqttForm';
import LoxForm from './LoxForm';

interface MessagingProtocolsFormProps {
  mqttData: any;
  loxData: any;
  onMqttChange: (data: any) => void;
  onLoxChange: (data: any) => void;
  onLoxValidationChange?: (isValid: boolean) => void;
}

/**
 * Combined form for all messaging protocols (MQTT, Lox UDP).
 * Renders tabbed interface with each protocol in its own tab,
 * each having an "Enabled" checkbox.
 */
const MessagingProtocolsForm: React.FC<MessagingProtocolsFormProps> = ({
  mqttData,
  loxData,
  onMqttChange,
  onLoxChange,
  onLoxValidationChange,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'mqtt' | 'lox_udp'>('mqtt');

  const mqttEnabled = mqttData?.enabled !== false; // default enabled
  const loxEnabled = loxData?.enabled === true; // default disabled

  const handleMqttEnabledChange = (enabled: boolean) => {
    onMqttChange({ ...mqttData, enabled });
  };

  const handleLoxEnabledChange = (enabled: boolean) => {
    if (enabled) {
      // Initialize lox_udp data if toggling on for the first time
      onLoxChange({ enabled: true, ...(loxData || {}), });
    } else {
      onLoxChange({ ...loxData, enabled: false });
      // When disabled, form is always valid (no host required)
      onLoxValidationChange?.(true);
    }
  };

  const handleLoxValidation = useCallback((isValid: boolean) => {
    onLoxValidationChange?.(isValid);
  }, [onLoxValidationChange]);

  return (
    <div className="space-y-0">
      <TabsBox
        name="messaging_tabs"
        activeTab={activeTab}
        onTabChange={(tabId) => setActiveTab(tabId as 'mqtt' | 'lox_udp')}
        bordered={false}
        tabs={[
          {
            id: 'mqtt',
            label: '📡 MQTT',
            content: (
              <div className="space-y-4">
                {/* Enabled checkbox */}
                <div className="form-control">
                  <label className="label cursor-pointer justify-start gap-4">
                    <input
                      type="checkbox"
                      className="toggle toggle-primary"
                      checked={mqttEnabled}
                      onChange={(e) => handleMqttEnabledChange(e.target.checked)}
                    />
                    <div className="flex flex-col">
                      <span className="label-text font-medium">{t('messaging.enable_mqtt')}</span>
                      <span className="label-text-alt text-base-content/60">{t('messaging.enable_mqtt_help')}</span>
                    </div>
                  </label>
                </div>

                {mqttEnabled ? (
                  <MqttForm data={mqttData} onChange={onMqttChange} />
                ) : (
                  <div className="alert">
                    <span>{t('messaging.mqtt_disabled_info')}</span>
                  </div>
                )}
              </div>
            ),
          },
          {
            id: 'lox_udp',
            label: '📨 Lox UDP',
            content: (
              <div className="space-y-4">
                {/* Enabled checkbox */}
                <div className="form-control">
                  <label className="label cursor-pointer justify-start gap-4">
                    <input
                      type="checkbox"
                      className="toggle toggle-primary"
                      checked={loxEnabled}
                      onChange={(e) => handleLoxEnabledChange(e.target.checked)}
                    />
                    <div className="flex flex-col">
                      <span className="label-text font-medium">{t('messaging.enable_lox')}</span>
                      <span className="label-text-alt text-base-content/60">{t('messaging.enable_lox_help')}</span>
                    </div>
                  </label>
                </div>

                {loxEnabled ? (
                  <LoxForm
                    data={loxData}
                    onChange={onLoxChange}
                    onValidationChange={handleLoxValidation}
                  />
                ) : (
                  <div className="alert">
                    <span>{t('messaging.lox_disabled_info')}</span>
                  </div>
                )}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default MessagingProtocolsForm;
