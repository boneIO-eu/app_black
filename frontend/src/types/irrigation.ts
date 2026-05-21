/**
 * Irrigation controller types used by IrrigationView and related components.
 */

export interface ZoneState {
  id: string;
  name: string;
  run_duration: number;
  enabled: boolean;
  run_every_n: number;
  skip_count: number;
}

export interface ScheduleEntry {
  index: number;
  time: string;
  days: string;
  skip: boolean;
}

export interface ActiveZone {
  id: string;
  name: string;
  remaining_s: number | null;
  end_utc: string | null;
}

export interface WaterSourceInfo {
  id: string;
  name: string;
  output_ids: string[];
}

export interface IrrigationController {
  id: string;
  name: string;
  state: 'IDLE' | 'RUNNING' | 'PAUSED';
  active_zone: ActiveZone | null;
  multiplier: number;
  repeat: number;
  auto_advance: boolean;
  reverse: boolean;
  standby: boolean;
  skip_next_run: boolean;
  pause_timeout_s: number;
  zones: ZoneState[];
  schedules: ScheduleEntry[];
  water_sources: WaterSourceInfo[];
  active_water_source: string | null;
}
