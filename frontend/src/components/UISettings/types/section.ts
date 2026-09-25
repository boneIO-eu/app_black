import type { ConfigRecord, JsonSchema } from '../../../types/jsonSchema';
import type {
  AreaEntity,
  BinarySensorEntity,
  CoverEntity,
  EventEntity,
  OutputEntity,
  RemoteDeviceEntity,
} from '../../../types/config';
import type { OutputGroupRecord } from '../ActionFields/types';

/** One settings section as UISettings holds it: its slice of the schema and its data. */
export interface ConfigSection {
  name: string;
  schema: JsonSchema;
  normalizedSchema: JsonSchema;
  uiSchema: ConfigRecord;
  /** The section's value from config.yaml: an object, or a list for array sections. */
  data: ConfigRecord | ConfigRecord[];
}

/**
 * Every section's form value, keyed by section name — the parsed config.yaml
 * plus the composite sections (local_inputs, board_sensors) merged in.
 *
 * The sections the settings page reads by name are spelled out; everything
 * else is reachable as `unknown`. Assignable to `Record<string, unknown>`.
 */
export interface SettingsFormData {
  boneio?: {
    name?: string;
    /** Board version; YAML may parse it as a number (0.5). */
    version?: string | number;
    device_type?: string;
    [key: string]: unknown;
  };
  output?: OutputEntity[];
  remote_outputs?: OutputEntity[];
  output_group?: OutputGroupRecord[];
  cover?: CoverEntity[];
  areas?: AreaEntity[];
  event?: EventEntity[];
  binary_sensor?: BinarySensorEntity[];
  /** Composite: binary_sensor + event, each item tagged with `_type`. */
  local_inputs?: ConfigRecord[];
  remote_inputs?: ConfigRecord[];
  remote_devices?: RemoteDeviceEntity[];
  sensor?: ConfigRecord[];
  lm75?: ConfigRecord[];
  mcp9808?: ConfigRecord[];
  modbus_devices?: ConfigRecord[];
  virtual_energy_sensor?: ConfigRecord[];
  virtual_switch?: ConfigRecord[];
  [section: string]: unknown;
}
