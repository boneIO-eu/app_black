export interface ThermostatState {
  id: string;
  name: string;
  mode: string;
  action: string;
  target_temperature: number;
  current_temperature: number | null;
}

export interface AlarmState {
  id: string;
  name: string;
  state: string;
  allow_frontend_control: boolean;
  code_required: boolean;
  code_arm_required: boolean;
  arming_remaining_s?: number;
  /** Seconds until codes are checked again after too many wrong ones. */
  code_locked_s?: number;
}

/** What became of an alarm command, as far as the PIN pad needs to know. */
export type AlarmCommandResult =
  | { ok: true }
  | { ok: false; reason: 'invalid_code' | 'code_required' | 'locked' | 'error'; retryAfter?: number };

export interface GateState {
  id: string;
  name: string;
  state: string;
  device_class: string;
  control_mode: string;
}

export interface TemplatesData {
  thermostats: ThermostatState[];
  alarms: AlarmState[];
  gates: GateState[];
}
