/**
 * Shared types for template configuration forms.
 */

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

export interface TemplateSubFormProps {
  data: any;
  onChange: (data: any) => void;
  onValidationChange?: (valid: boolean) => void;
  allOutputs: any[];
  allAreas: Area[];
  allSensors: any[];
  allInputs: any[];
  allRemoteInputs: any[];
  allModbusDevices: any[];
}

export interface TemplateFormProps extends TemplateSubFormProps {
  schema?: any;
  onValidationChange?: (valid: boolean) => void;
}

export const PLATFORM_OPTIONS = ['thermostat', 'alarm_control_panel', 'gate_cover', 'irrigation'] as const;
export const ARM_MODE_OPTIONS = ['armed_away', 'armed_home', 'armed_night'] as const;
export const OUTPUT_TYPE_OPTIONS = ['siren', 'light', 'custom'] as const;
export const GATE_CONTROL_MODES = ['cycle', 'separate', 'open_only'] as const;
export const GATE_DEVICE_CLASSES = ['gate', 'garage_door', 'barrier', 'door'] as const;
export const SCHEDULE_DAY_OPTIONS = ['daily', 'weekdays', 'weekend', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;
