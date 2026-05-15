export type ExpanderBoardType = '32x10A' | '24x16A' | 'cover' | 'cover_mix';

type ChipRole = 'left' | 'right';

interface OutputSlot {
  slotId: string;
  chipRole: ChipRole;
  pin: number;
  outputType: string;
}

export interface BoardDefinition {
  type: ExpanderBoardType;
  label: string;
  outputs: OutputSlot[];
}

// Universal expander pin mapping (always 2 chips: expander_left / expander_right)
// Pattern: left pins 0-7, right pins 0-7, left pins 15-8, right pins 15-8
function makeRegularSlots(count: number): OutputSlot[] {
  const slots: OutputSlot[] = [];
  const groups: Array<{ role: ChipRole; pins: number[] }> = [
    { role: 'left',  pins: [0,1,2,3,4,5,6,7] },
    { role: 'right', pins: [0,1,2,3,4,5,6,7] },
    { role: 'left',  pins: [15,14,13,12,11,10,9,8] },
    { role: 'right', pins: [15,14,13,12,11,10,9,8] },
  ];
  let n = 1;
  for (const { role, pins } of groups) {
    for (const pin of pins) {
      if (n > count) break;
      slots.push({
        slotId: `EX_OUT_${String(n).padStart(2, '0')}`,
        chipRole: role,
        pin,
        outputType: 'light',
      });
      n++;
    }
    if (n > count) break;
  }
  return slots;
}

function makeCoverSlots(pairs: number): OutputSlot[] {
  const slots: OutputSlot[] = [];
  const groups: Array<{ role: ChipRole; startPin: number; dir: 1 | -1 }> = [
    { role: 'left',  startPin: 0,  dir: 1 },
    { role: 'right', startPin: 0,  dir: 1 },
    { role: 'left',  startPin: 15, dir: -1 },
    { role: 'right', startPin: 15, dir: -1 },
  ];
  let pairNum = 1;
  for (const { role, startPin, dir } of groups) {
    for (let i = 0; i < 4; i++) {
      if (pairNum > pairs) break;
      const nn = String(pairNum).padStart(2, '0');
      slots.push({ slotId: `EX_${nn}_up`,   chipRole: role, pin: startPin + i * 2 * dir,     outputType: 'cover' });
      slots.push({ slotId: `EX_${nn}_down`, chipRole: role, pin: startPin + (i * 2 + 1) * dir, outputType: 'cover' });
      pairNum++;
    }
    if (pairNum > pairs) break;
  }
  return slots;
}

export const EXPANDER_BOARDS: Record<ExpanderBoardType, BoardDefinition> = {
  '32x10A': {
    type: '32x10A',
    label: '32×10A (32 outputs)',
    outputs: makeRegularSlots(32),
  },
  '24x16A': {
    type: '24x16A',
    label: '24×16A (24 outputs)',
    outputs: makeRegularSlots(24),
  },
  'cover': {
    type: 'cover',
    label: 'Cover (16 covers = 32 channels)',
    outputs: makeCoverSlots(16),
  },
  'cover_mix': {
    type: 'cover_mix',
    label: 'Cover Mix (8 covers + 16 outputs)',
    outputs: [
      ...makeCoverSlots(8),
      ...makeRegularSlots(32).slice(16), // OUT_17–OUT_32 positions
    ],
  },
};

export function generateExpanderOutputEntries(boardType: ExpanderBoardType): any[] {
  const board = EXPANDER_BOARDS[boardType];
  return board.outputs.map(slot => ({
    id: slot.slotId,
    kind: 'mcp',
    mcp_id: `expander_${slot.chipRole}`,
    pin: slot.pin,
    output_type: slot.outputType,
  }));
}

export const EXPANDER_OUTPUT_PREFIX = 'EX_';

export function isExpanderOutput(boneioOutput: string | undefined): boolean {
  return typeof boneioOutput === 'string' && boneioOutput.startsWith(EXPANDER_OUTPUT_PREFIX);
}

/** Detect expander board type from a list of EX_* output entries. */
export function detectExpanderBoardType(exOutputs: any[]): ExpanderBoardType | null {
  if (exOutputs.length === 0) return null;
  const types = exOutputs.map((o: any) => (o.output_type || '').toLowerCase());
  const allCover = types.every(t => t === 'cover');
  const hasCover = types.some(t => t === 'cover');
  const hasNonCover = types.some(t => t !== 'cover');
  if (allCover) return 'cover';
  if (hasCover && hasNonCover) return 'cover_mix';
  return exOutputs.length <= 24 ? '24x16A' : '32x10A';
}
