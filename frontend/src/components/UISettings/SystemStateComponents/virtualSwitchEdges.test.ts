import { describe, it, expect } from 'vitest';
import { withEdgeActions, type SwitchEntry } from './virtualSwitchEdges';

const ON = { action: 'output', boneio_output: 'out_01', action_output: 'ON' };
const OFF = { action: 'output', boneio_output: 'out_01', action_output: 'OFF' };

describe('withEdgeActions', () => {
  it('adds a list to a switch that had none', () => {
    const result = withEdgeActions({ id: 'away' }, 'on_turn_on', [ON]);
    expect(result.actions).toEqual({ on_turn_on: [ON] });
  });

  it('leaves the other edge alone', () => {
    const entry: SwitchEntry = { id: 'away', actions: { on_turn_off: [OFF] } };
    const result = withEdgeActions(entry, 'on_turn_on', [ON]);
    expect(result.actions).toEqual({ on_turn_on: [ON], on_turn_off: [OFF] });
  });

  it('removes an edge that was emptied, instead of leaving on_turn_on: []', () => {
    const entry: SwitchEntry = { id: 'away', actions: { on_turn_on: [ON], on_turn_off: [OFF] } };
    const result = withEdgeActions(entry, 'on_turn_on', []);
    expect(result.actions).toEqual({ on_turn_off: [OFF] });
  });

  it('drops actions entirely once the last edge is emptied', () => {
    const entry: SwitchEntry = { id: 'away', actions: { on_turn_on: [ON] } };
    const result = withEdgeActions(entry, 'on_turn_on', []);
    expect('actions' in result).toBe(false);
  });

  it('is a no-op on a switch that never had actions', () => {
    const result = withEdgeActions({ id: 'away', name: 'Away' }, 'on_turn_off', []);
    expect(result).toEqual({ id: 'away', name: 'Away' });
  });

  it('does not mutate the switch it was given', () => {
    const entry: SwitchEntry = { id: 'away', actions: { on_turn_on: [ON] } };
    withEdgeActions(entry, 'on_turn_off', [OFF]);
    expect(entry.actions).toEqual({ on_turn_on: [ON] });
  });
});
