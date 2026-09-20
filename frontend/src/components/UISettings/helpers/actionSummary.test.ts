import { describe, it, expect } from 'vitest';
import { actionIsIncomplete, actionSummary, conditionCount } from './actionSummary';

/** The real translator falls back to the key; `actions.*` are the verbs. */
const VERBS: Record<string, string> = {
  'actions.on': 'Turn on',
  'actions.off': 'Turn off',
  'actions.toggle': 'Toggle',
  'actions.open': 'Open',
  'event_form.conditions': 'conditions',
  'actions.delay_execution': 'after',
};
const t = (key: string) => VERBS[key] ?? key;

const OUTPUTS = [{ id: 'out_01', boneio_output: 'out_01', name: 'Living room' }];

describe('actionSummary', () => {
  it('names the output by the name someone gave it', () => {
    const line = actionSummary(
      { action: 'output', boneio_output: 'out_01', action_output: 'ON' },
      t,
      { allOutputs: OUTPUTS },
    );
    expect(line).toBe('Turn on: Living room');
  });

  it('falls back to the id when the output has no name', () => {
    const line = actionSummary({ action: 'output', boneio_output: 'out_09', action_output: 'OFF' }, t);
    expect(line).toBe('Turn off: out_09');
  });

  it('defaults the verb the way the schema does', () => {
    expect(actionSummary({ action: 'output', boneio_output: 'out_09' }, t)).toBe('Toggle: out_09');
  });

  it('describes a cover', () => {
    const line = actionSummary({ action: 'cover', boneio_cover: 'blind_1', action_cover: 'OPEN' }, t);
    expect(line).toBe('Open: blind_1');
  });

  it('describes an mqtt publish by its topic', () => {
    expect(actionSummary({ action: 'mqtt', topic: 'house/bell' }, t)).toBe('MQTT: house/bell');
  });

  it('counts a single condition', () => {
    const line = actionSummary(
      { action: 'output', boneio_output: 'out_01', action_output: 'ON', condition: { type: 'sun' } },
      t,
      { allOutputs: OUTPUTS },
    );
    expect(line).toBe('Turn on: Living room · conditions: 1');
  });

  it('counts a condition list', () => {
    const line = actionSummary(
      {
        action: 'output',
        boneio_output: 'out_01',
        conditions: { mode: 'and', list: [{ type: 'sun' }, { type: 'time' }] },
      },
      t,
      { allOutputs: OUTPUTS },
    );
    expect(line).toBe('Toggle: Living room · conditions: 2');
  });

  it('says the action type when nothing is filled in yet', () => {
    // Never a dangling verb or a lone arrow: a fresh row is added before it is
    // pointed at anything, and that row still has to read as something.
    expect(actionSummary({ action: 'mqtt' }, t)).toBe('MQTT');
    expect(actionSummary({ action: 'output' }, t)).toBe('Toggle');
  });

  it('drops the separator of a remote target that is not chosen yet', () => {
    expect(actionSummary({ action: 'remote_output', action_output: 'ON', output_id: 'lamp' }, t))
      .toBe('Turn on: lamp');
  });
});

describe('conditionCount', () => {
  it('is zero for an action with none', () => {
    expect(conditionCount({ action: 'output' })).toBe(0);
  });

  it('reads both shapes', () => {
    expect(conditionCount({ condition: { type: 'sun' } })).toBe(1);
    expect(conditionCount({ conditions: { list: [1, 2, 3] } })).toBe(3);
  });
});

describe('actionIsIncomplete', () => {
  it('flags an action with no target', () => {
    expect(actionIsIncomplete({ action: 'output' })).toBe(true);
    expect(actionIsIncomplete({ action: 'output', boneio_output: 'out_01' })).toBe(false);
  });

  it('needs both halves of a remote target', () => {
    expect(actionIsIncomplete({ action: 'remote_output', output_id: 'lamp' })).toBe(true);
    expect(actionIsIncomplete({ action: 'remote_output', output_id: 'lamp', remote_device: 'esp' })).toBe(false);
  });
});
