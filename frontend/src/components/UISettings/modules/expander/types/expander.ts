export type ExpanderBoardType = '32x10A' | '24x16A' | 'cover' | 'cover_mix';

export type ChipRole = 'left' | 'right';

export interface ExpanderOutputSlot {
  slotId: string;
  chipRole: ChipRole;
  pin: number;
  outputType: string;
}

export interface ExpanderBoardDefinition {
  type: ExpanderBoardType;
  label: string;
  outputs: ExpanderOutputSlot[];
}

export interface ExpanderOutputStats {
  boardCapacity: number;
  boardUsed: number;
  expanderCapacity: number;
  expanderUsed: number;
}
