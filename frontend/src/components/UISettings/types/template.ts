/**
 * Shared types for template configuration forms.
 */

import type { JsonSchema } from '@/types/jsonSchema';
import type { OutputEntity } from '@/types/config';
import type { SensorConfigEntry, ModbusDeviceEntry } from '../helpers/thermostatHelpers';

export interface Area {
  id: string;
  name: string;
}

export interface ZoneInput {
  id: string;
  type: 'normally_closed' | 'normally_open';
  /** 'local' (default) or 'remote' — distinguishes local GPIO vs remote device inputs. */
  source?: 'local' | 'remote';
  /** Behavior when remote device loses connection: 'ignore' (skip sensor) or 'trigger' (trigger alarm). */
  on_disconnect?: 'ignore' | 'trigger';
}

export interface AlarmZone {
  name: string;
  inputs: (string | ZoneInput)[];
  arm_modes: string[];
  entry_delay: boolean;
}

export interface AlarmOutput {
  id: string;
  type: string;
}

export interface AlarmPin {
  name: string;
  code: string;
}

export interface AlarmPanelData {
  platform?: string;
  id?: string;
  name?: string;
  area?: string;
  zones?: AlarmZone[];
  codes?: AlarmPin[];
  outputs?: AlarmOutput[];
  arming_time?: string;
  delay_time?: string;
  trigger_time?: string;
  code_arm_required?: boolean;
  allow_frontend_control?: boolean;
}

export interface GateCoverData {
  platform?: string;
  id?: string;
  name?: string;
  area?: string;
  control_mode?: string;
  device_class?: string;
  open_output?: string;
  close_output?: string;
  stop_output?: string;
  pulse_output?: string;
  pulse_duration?: string | number;
  closed_sensor?: string;
  open_sensor?: string;
}

/**
 * Fields every template item carries. A type alias (not an interface) so it
 * stays assignable to `Record<string, unknown>` for generic callers.
 */
export type TemplateData = {
  platform?: string;
  id?: string;
  name?: string;
  area?: string;
};

/** Local binary-sensor input as the template forms read it. */
export interface TemplateInputEntry {
  id?: string;
  boneio_input?: string;
  name?: string;
  area?: string;
  /** Tag added by the input aggregator ('binary_sensor' or absent). */
  kind?: string;
}

/** Binary sensor exposed by a remote device. */
export interface TemplateRemoteInputEntry {
  id?: string;
  name?: string;
  device_id?: string;
  input_id?: string;
  remote_source?: string;
}

export interface TemplateSubFormProps<D = TemplateData> {
  data: D;
  onChange: (data: D) => void;
  onValidationChange?: (valid: boolean) => void;
  allOutputs: OutputEntity[];
  allAreas: Area[];
  allSensors: SensorConfigEntry[];
  allInputs: TemplateInputEntry[];
  allRemoteInputs: TemplateRemoteInputEntry[];
  allModbusDevices: ModbusDeviceEntry[];
}

export interface TemplateFormProps extends TemplateSubFormProps {
  schema?: JsonSchema;
  onValidationChange?: (valid: boolean) => void;
}

export const PLATFORM_OPTIONS = ['thermostat', 'alarm_control_panel', 'gate_cover', 'irrigation'] as const;
export const ARM_MODE_OPTIONS = ['armed_away', 'armed_home', 'armed_night'] as const;
export const OUTPUT_TYPE_OPTIONS = ['siren', 'light', 'custom'] as const;
export const GATE_CONTROL_MODES = ['cycle', 'separate', 'open_only'] as const;
export const GATE_DEVICE_CLASSES = ['gate', 'garage_door', 'barrier', 'door'] as const;
export const SCHEDULE_DAY_OPTIONS = ['daily', 'weekdays', 'weekend', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;
