import React from 'react';
import type { MqttActionProps } from './types';

/**
 * MQTT Action component - handles direct MQTT message publishing.
 */
const MqttAction: React.FC<MqttActionProps> = ({
  action,
  onUpdate,
  t,
}) => {
  return (
    <>
      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.mqtt_topic')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          placeholder={t('event_form.mqtt_topic_placeholder')}
          value={action.topic || ''}
          onChange={(e) => onUpdate('topic', e.target.value)}
        />
      </div>

      <div className="form-control mb-3">
        <label className="label">
          <span className="label-text font-medium">{t('event_form.mqtt_message')}</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          placeholder={t('event_form.mqtt_message_placeholder')}
          value={action.action_mqtt_msg || ''}
          onChange={(e) => onUpdate('action_mqtt_msg', e.target.value)}
        />
      </div>
    </>
  );
};

export default MqttAction;
