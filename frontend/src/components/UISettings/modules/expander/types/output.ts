export type OutputKind = 'board' | 'expander';
export type OutputType = 'switch' | 'light' | 'valve' | 'cover';

export interface OutputEntity {
  id?: string;
  name?: string;
  boneio_output?: string;
  output_type?: OutputType;
  kind?: string;
  mcp_id?: string;
  pin?: number | string;
  area?: string;
  interlock_group?: string;
  restore_state?: boolean;
  momentary_turn_on?: unknown;
  momentary_turn_off?: unknown;
}
