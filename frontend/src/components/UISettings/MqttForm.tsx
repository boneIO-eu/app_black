import React from 'react';

interface MqttFormProps {
  data: any;
  onChange: (data: any) => void;
}

/**
 * Custom form for MQTT section configuration.
 * Fields: host, username, password, port, topic_prefix, ha_discovery
 */
const MqttForm: React.FC<MqttFormProps> = ({ data, onChange }) => {
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
          <span className="label-text font-medium">Host <span className="text-error">*</span></span>
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
          <span className="label-text-alt text-base-content/60">MQTT broker hostname or IP address</span>
        </label>
      </div>

      {/* Port */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Port</span>
        </label>
        <input
          type="number"
          className="input input-bordered w-full"
          value={data?.port ?? 1883}
          onChange={(e) => handleChange('port', parseInt(e.target.value) || 1883)}
          placeholder="1883"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Port to connect to MQTT broker (default: 1883)</span>
        </label>
      </div>

      {/* Username */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Username</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.username || ''}
          onChange={(e) => handleChange('username', e.target.value || undefined)}
          placeholder="mqtt_user"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Username to connect to MQTT broker (optional)</span>
        </label>
      </div>

      {/* Password */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Password</span>
        </label>
        <input
          type="password"
          className="input input-bordered w-full"
          value={data?.password || ''}
          onChange={(e) => handleChange('password', e.target.value || undefined)}
          placeholder="••••••••"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Password to MQTT broker (optional)</span>
        </label>
      </div>

      {/* Topic Prefix */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">Topic Prefix</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.topic_prefix || ''}
          onChange={(e) => handleChange('topic_prefix', e.target.value || undefined)}
          placeholder="boneio"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Prefix topic for boneIO. If not set, uses device name.</span>
        </label>
      </div>

      {/* HA Discovery Section */}
      <div className="divider">Home Assistant Discovery</div>

      {/* HA Discovery Enabled */}
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            checked={data?.ha_discovery?.enabled ?? true}
            onChange={(e) => handleHaDiscoveryChange('enabled', e.target.checked)}
          />
          <span className="label-text font-medium">Enable HA Discovery</span>
        </label>
        <label className="label">
          <span className="label-text-alt text-base-content/60">Automatically register devices in Home Assistant</span>
        </label>
      </div>

      {/* HA Discovery Topic Prefix */}
      <div className="form-control">
        <label className="label">
          <span className="label-text font-medium">HA Discovery Topic Prefix</span>
        </label>
        <input
          type="text"
          className="input input-bordered w-full"
          value={data?.ha_discovery?.topic_prefix || 'homeassistant'}
          onChange={(e) => handleHaDiscoveryChange('topic_prefix', e.target.value || 'homeassistant')}
          placeholder="homeassistant"
        />
        <label className="label">
          <span className="label-text-alt text-base-content/60">Prefix topic of HA discovery (default: homeassistant)</span>
        </label>
      </div>
    </div>
  );
};

export default MqttForm;
