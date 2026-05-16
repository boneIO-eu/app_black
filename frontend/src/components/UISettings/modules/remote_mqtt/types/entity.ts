/** Shapes for generic-MQTT remote inputs / outputs (matches backend schema). */

export type MqttEntityKind = 'binary_sensor' | 'sensor' | 'event' | 'switch' | 'light';

/** Remote input config row for `protocol: mqtt_generic`. */
export interface MqttRemoteInput {
  id: string;
  name?: string;
  protocol: 'mqtt_generic';
  topic: string;
  /** Jinja2 template, default `{{ value }}`. */
  value_template?: string;
  /** For binary mode — raw payload that should map to `true`. */
  payload_on?: string;
  /** For binary mode — raw payload that should map to `false`. */
  payload_off?: string;
  qos?: 0 | 1 | 2;
  mode?: 'binary_sensor' | 'event';
}

/** Remote output config row for `protocol: mqtt_generic`. */
export interface MqttRemoteOutput {
  id: string;
  name?: string;
  protocol: 'mqtt_generic';
  /** Topic to publish commands to (turn_on / turn_off). */
  topic: string;
  /** Jinja2 template rendering the outgoing payload; default `{{ state }}`. */
  command_template?: string;
  /** Optional topic to subscribe for state feedback. */
  state_topic?: string;
  /** Jinja2 template extracting state from `state_topic` payload. */
  state_value_template?: string;
  qos?: 0 | 1 | 2;
  retain?: boolean;
}
