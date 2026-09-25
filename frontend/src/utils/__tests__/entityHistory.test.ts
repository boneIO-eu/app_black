import { beforeEach, describe, expect, it } from 'vitest';
import {
  MAX_ENTRIES,
  getEntityHistory,
  historyKey,
  recordFromStateUpdate,
  recordIrrigation,
  recordTemplates,
  resetEntityHistory,
} from '../entityHistory';
import type { CoverEvent, InputEvent, OutputEvent } from '@/hooks/useWebSocket';

const output = (state: string, timestamp: number, brightness?: number): OutputEvent => ({
  event_type: 'output',
  entity_id: 'out_01',
  state: {
    id: 'out_01', name: 'OUT 01', state, type: 'light', expander_id: null, pin: 1,
    timestamp, area: null, interlock_groups: [], brightness,
  },
});

const input = (state: string, timestamp: number, duration: number | null = null): InputEvent => ({
  event_type: 'input',
  entity_id: 'in_07',
  click_type: state,
  duration,
  state: { name: 'IN_07', state, type: 'input', pin: 'P8_1', timestamp, boneio_input: 'in_07', area: null },
});

const cover = (state: string, current_operation: string, position: number, timestamp: number): CoverEvent => ({
  event_type: 'cover',
  entity_id: 'cover_1',
  state: { id: 'blind', name: 'Blind', state, position, current_operation, timestamp, tilt: 0, kind: 'time_based' },
});

describe('entityHistory', () => {
  beforeEach(() => resetEntityHistory());

  it('starts from the snapshot, with its real timestamp', () => {
    recordFromStateUpdate(output('ON', 1_790_000_000));
    expect(getEntityHistory(historyKey('output', 'out_01'))).toEqual([
      { at: 1_790_000_000_000, value: 'ON', detail: undefined },
    ]);
  });

  it('records output changes newest first, and ignores a resync of the same state', () => {
    recordFromStateUpdate(output('ON', 100));
    recordFromStateUpdate(output('ON', 100)); // resync after reconnect
    recordFromStateUpdate(output('OFF', 200));
    const list = getEntityHistory(historyKey('output', 'out_01'));
    expect(list.map(e => e.value)).toEqual(['OFF', 'ON']);
  });

  it('treats a brightness change while on as a new entry', () => {
    recordFromStateUpdate(output('ON', 100, 255));
    recordFromStateUpdate(output('ON', 110, 128));
    expect(getEntityHistory(historyKey('output', 'out_01')).map(e => e.detail)).toEqual(['50%', '100%']);
  });

  it('keeps every input click, even a repeat of the same type', () => {
    recordFromStateUpdate(input('single', 100));
    recordFromStateUpdate(input('single', 101));
    recordFromStateUpdate(input('single', 101)); // the same event delivered twice
    recordFromStateUpdate(input('long', 102, 1.26));
    const list = getEntityHistory(historyKey('input', 'in_07'));
    expect(list.map(e => [e.value, e.detail])).toEqual([['long', '1.3s'], ['single', undefined], ['single', undefined]]);
  });

  it('does not list an input that has not fired since boot', () => {
    // The snapshot sends it as "Unknown" with no time, once per resync.
    recordFromStateUpdate({ ...input('Unknown', 0), state: { ...input('Unknown', 0).state, timestamp: 0 } });
    recordFromStateUpdate({ ...input('Unknown', 0), state: { ...input('Unknown', 0).state, timestamp: 0 } });
    expect(getEntityHistory(historyKey('input', 'in_07'))).toEqual([]);
  });

  it('keeps cover moves and where they ended, not every position report', () => {
    recordFromStateUpdate(cover('closed', 'idle', 0, 100));
    recordFromStateUpdate(cover('open', 'opening', 10, 101));
    recordFromStateUpdate(cover('open', 'opening', 30, 102));
    recordFromStateUpdate(cover('open', 'opening', 60, 103));
    recordFromStateUpdate(cover('open', 'idle', 60, 104));
    const list = getEntityHistory(historyKey('cover', 'blind'));
    expect(list.map(e => [e.value, e.detail])).toEqual([['open', '60%'], ['opening', undefined], ['closed', '0%']]);
  });

  it(`keeps at most ${MAX_ENTRIES} entries`, () => {
    for (let i = 0; i < MAX_ENTRIES + 5; i++) recordFromStateUpdate(input('single', 1000 + i));
    const list = getEntityHistory(historyKey('input', 'in_07'));
    expect(list).toHaveLength(MAX_ENTRIES);
    expect(list[0].at).toBe((1000 + MAX_ENTRIES + 4) * 1000);
  });

  it('returns the same array until something changes', () => {
    recordFromStateUpdate(output('ON', 100));
    const before = getEntityHistory(historyKey('output', 'out_01'));
    recordFromStateUpdate(output('ON', 100));
    expect(getEntityHistory(historyKey('output', 'out_01'))).toBe(before);
  });

  it('records polled templates only when their state changes', () => {
    const th = { id: 'th', name: 'T', mode: 'heat', action: 'idle', target_temperature: 21, current_temperature: 20 };
    recordTemplates({ thermostats: [th], alarms: [], gates: [] });
    recordTemplates({ thermostats: [{ ...th, current_temperature: 20.5 }], alarms: [], gates: [] });
    recordTemplates({ thermostats: [{ ...th, action: 'heating' }], alarms: [], gates: [] });
    expect(getEntityHistory(historyKey('thermostat', 'th')).map(e => e.value)).toEqual(['heating', 'idle']);
  });

  it('records the running irrigation zone', () => {
    const base = {
      id: 'irr', name: 'Garden', multiplier: 1, repeat: 1, auto_advance: true, reverse: false, standby: false,
      skip_next_run: false, pause_timeout_s: 0, zones: [], schedules: [], water_sources: [], active_water_source: null,
    };
    recordIrrigation([{ ...base, state: 'IDLE', active_zone: null }]);
    recordIrrigation([{ ...base, state: 'RUNNING', active_zone: { id: 'z1', name: 'Lawn', remaining_s: 60, end_utc: null } }]);
    recordIrrigation([{ ...base, state: 'RUNNING', active_zone: { id: 'z2', name: 'Beds', remaining_s: 60, end_utc: null } }]);
    expect(getEntityHistory(historyKey('irrigation', 'irr')).map(e => [e.value, e.detail]))
      .toEqual([['RUNNING', 'Beds'], ['RUNNING', 'Lawn'], ['IDLE', undefined]]);
  });
});
