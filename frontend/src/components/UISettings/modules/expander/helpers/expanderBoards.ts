/**
 * Board definitions, slot generators, expander predicates and output stats.
 * Pure functions only — no React, no side-effects.
 */
import type { OutputEntity } from '../types/output';
import type {
  ExpanderBoardType,
  ExpanderBoardDefinition,
  ExpanderOutputSlot,
  ExpanderOutputStats,
  ChipRole,
} from '../types/expander';

export const EXPANDER_OUTPUT_PREFIX = 'EX_';

/**
 * Single source of truth for detecting expander outputs.
 * Accepts an OutputEntity-shaped object OR a bare string (id/boneio_output).
 */
export function isExpanderOutput(
  input: Partial<OutputEntity> | string | null | undefined,
): boolean {
  if (input == null) return false;
  if (typeof input === 'string') return input.startsWith(EXPANDER_OUTPUT_PREFIX);
  const value = input.id || input.boneio_output || '';
  return value.startsWith(EXPANDER_OUTPUT_PREFIX);
}

function makeRegularSlots(count: number): ExpanderOutputSlot[] {
  const slots: ExpanderOutputSlot[] = [];
  const groups: Array<{ role: ChipRole; pins: number[] }> = [
    { role: 'left',  pins: [0, 1, 2, 3, 4, 5, 6, 7] },
    { role: 'right', pins: [0, 1, 2, 3, 4, 5, 6, 7] },
    { role: 'left',  pins: [15, 14, 13, 12, 11, 10, 9, 8] },
    { role: 'right', pins: [15, 14, 13, 12, 11, 10, 9, 8] },
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

function makeCoverSlots(pairs: number): ExpanderOutputSlot[] {
  const slots: ExpanderOutputSlot[] = [];
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
      slots.push({ slotId: `EX_${nn}_up`,   chipRole: role, pin: startPin + i * 2 * dir,         outputType: 'cover' });
      slots.push({ slotId: `EX_${nn}_down`, chipRole: role, pin: startPin + (i * 2 + 1) * dir,   outputType: 'cover' });
      pairNum++;
    }
    if (pairNum > pairs) break;
  }
  return slots;
}

export const EXPANDER_BOARDS: Record<ExpanderBoardType, ExpanderBoardDefinition> = {
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
      ...makeRegularSlots(32).slice(16),
    ],
  },
};

export function generateExpanderOutputEntries(boardType: ExpanderBoardType): OutputEntity[] {
  const board = EXPANDER_BOARDS[boardType];
  return board.outputs.map((slot) => ({
    id: slot.slotId,
    kind: 'mcp',
    mcp_id: `expander_${slot.chipRole}`,
    pin: slot.pin,
    output_type: slot.outputType as OutputEntity['output_type'],
  }));
}

/** Detect expander board type from a list of EX_* output entries. */
export function detectExpanderBoardType(
  exOutputs: OutputEntity[],
): ExpanderBoardType | null {
  if (exOutputs.length === 0) return null;
  const types = exOutputs.map((o) => (o.output_type || '').toLowerCase());
  const allCover = types.every((t) => t === 'cover');
  const hasCover = types.some((t) => t === 'cover');
  const hasNonCover = types.some((t) => t !== 'cover');
  if (allCover) return 'cover';
  if (hasCover && hasNonCover) return 'cover_mix';
  return exOutputs.length <= 24 ? '24x16A' : '32x10A';
}

/**
 * Compute board and expander slot capacity statistics for the output section.
 * Used by the dropdown Add button to show used/capacity per type.
 */
export function getOutputStats(
  value: OutputEntity[],
  deviceType: string | undefined,
): ExpanderOutputStats {
  const type = (deviceType || '').toLowerCase();
  let boardCapacity: number;
  if (type.includes('32') || type.includes('cm')) boardCapacity = 32;
  else if (type.includes('24')) boardCapacity = 24;
  else boardCapacity = 49;

  const boardUsed = value.filter(
    (o) => o.boneio_output && !isExpanderOutput(o.boneio_output),
  ).length;

  const usedExIds = new Set<string>(
    value
      .map((o) => (isExpanderOutput(o) ? (o.id || o.boneio_output) : null))
      .filter((v): v is string => typeof v === 'string'),
  );

  let expanderCapacity = 0;
  if (usedExIds.size > 0) {
    for (const board of Object.values(EXPANDER_BOARDS)) {
      const matchCount = board.outputs.filter((o) => usedExIds.has(o.slotId)).length;
      if (matchCount > 0) expanderCapacity = Math.max(expanderCapacity, board.outputs.length);
    }
  }

  return { boardCapacity, boardUsed, expanderCapacity, expanderUsed: usedExIds.size };
}
