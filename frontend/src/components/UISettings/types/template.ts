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
  allOutputs: any[];
  allAreas: Area[];
  allSensors: any[];
  allInputs: any[];
  allModbusDevices: any[];
  onValidationChange?: (hasErrors: boolean) => void;
}

export interface TemplateFormProps extends TemplateSubFormProps {
  schema?: any;
}

export const PLATFORM_OPTIONS = ['thermostat', 'alarm_control_panel', 'gate_cover'] as const;
export const ARM_MODE_OPTIONS = ['armed_away', 'armed_home', 'armed_night'] as const;
export const OUTPUT_TYPE_OPTIONS = ['siren', 'light', 'custom'] as const;
export const GATE_CONTROL_MODES = ['cycle', 'separate', 'open_only'] as const;
export const GATE_DEVICE_CLASSES = ['gate', 'garage_door', 'barrier', 'door'] as const;
