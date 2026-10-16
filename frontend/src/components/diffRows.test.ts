import { describe, expect, it } from 'vitest';
import { parseDiff } from './diffRows';

const DIFF = [
  '--- output (now)',
  '+++ output (proposed)',
  '@@ -1,3 +1,3 @@',
  ' - name: OUT 01',
  '-  output_type: light',
  '+  output_type: switch',
  '   pin: 7',
  '@@ -20,2 +20,3 @@',
  ' - name: OUT 03',
  '+  area: kuchnia',
  '   pin: 5',
].join('\n');

describe('parseDiff', () => {
  it('numbers lines as they will stand and marks the gaps between hunks', () => {
    const { rows, added, removed } = parseDiff(DIFF);
    expect([added, removed]).toEqual([2, 1]);
    expect(rows).toEqual([
      { kind: 'ctx', text: '- name: OUT 01', line: 1 },
      { kind: 'del', text: '  output_type: light', line: null },
      { kind: 'add', text: '  output_type: switch', line: 2 },
      { kind: 'ctx', text: '  pin: 7', line: 3 },
      { kind: 'gap' },
      { kind: 'ctx', text: '- name: OUT 03', line: 20 },
      { kind: 'add', text: '  area: kuchnia', line: 21 },
      { kind: 'ctx', text: '  pin: 5', line: 22 },
    ]);
  });

  it('has nothing to draw for no change', () => {
    expect(parseDiff('').rows).toEqual([]);
  });
});
