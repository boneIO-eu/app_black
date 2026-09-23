import { describe, it, expect } from 'vitest';
import {
  PRESENCE_FLAG,
  buildPresenceSimulation,
  isGenerated,
  mergeGenerated,
  type PresenceOptions,
} from './presenceSimulation';

const OPTIONS: PresenceOptions = {
  lights: ['out_living', 'out_bedroom'],
  endsAt: '23:10',
  randomness: 'normal',
};

const build = (overrides: Partial<PresenceOptions> = {}) =>
  buildPresenceSimulation({ ...OPTIONS, ...overrides });

describe('buildPresenceSimulation', () => {
  it('makes one schedule per light plus the one that ends the evening', () => {
    const { schedules } = build();
    expect(schedules.map((s) => s.id)).toEqual([
      'presence_step_1',
      'presence_step_2',
      'presence_off',
    ]);
  });

  it('anchors the first light to dusk so it follows the season', () => {
    const { schedules } = build();
    expect(schedules[0].trigger).toMatchObject({ type: 'sun', event: 'civil_dusk' });
  });

  it('caps dusk two hours before bedtime', () => {
    // Midsummer dusk here is 21:50; without this the evening would be eighty
    // minutes long in exactly the season the house is empty.
    const { schedules } = build();
    expect(schedules[0].trigger).toMatchObject({ latest: '21:10' });
  });

  it('places the later lights inside the evening window, not relative to dusk', () => {
    // Dusk is 15:30 in December here. A step placed relative to it would put
    // the bedroom light on at four in the afternoon.
    const { schedules } = build();
    expect(schedules[1].trigger).toMatchObject({ type: 'time', at: '22:10' });
  });

  it('keeps the steps in order and apart however many lights there are', () => {
    // Fixed hourly gaps counted back from bedtime put the second light on the
    // cap at three lights, and *before* the first light at four.
    for (const count of [1, 2, 3, 4, 5]) {
      const lights = Array.from({ length: count }, (_, i) => `out_${i}`);
      const { preview } = build({ lights });
      const times = preview.map((line) => line.at.replace('~', ''));
      expect(new Set(times).size, `${count} lights: ${times.join(', ')}`).toBe(times.length);
      expect([...times].sort(), `${count} lights not in order`).toEqual(times);
    }
  });

  it('turns the previous light off as the next comes on', () => {
    const { schedules } = build();
    const actions = schedules[1].actions as Record<string, unknown>[];
    expect(actions).toEqual([
      { action: 'output', boneio_output: 'out_living', action_output: 'OFF', probability: 0.85 },
      { action: 'output', boneio_output: 'out_bedroom', action_output: 'ON', probability: 0.85 },
    ]);
  });

  it('never puts a probability on turning things off at the end', () => {
    // A step that might not happen is realistic. A light that might not go off
    // burns until morning and announces that nobody is home.
    const { schedules } = build({ randomness: 'lively' });
    const off = schedules[schedules.length - 1].actions as Record<string, unknown>[];
    expect(off.every((action) => !('probability' in action))).toBe(true);
  });

  it('leaves out probability entirely when asked for calm', () => {
    const { schedules } = build({ randomness: 'calm' });
    const actions = schedules[0].actions as Record<string, unknown>[];
    expect(actions[0].probability).toBe(1);
    expect(schedules[0].trigger).toMatchObject({ jitter: '15min' });
  });

  it('gates every schedule on the flag', () => {
    const { schedules } = build();
    for (const schedule of schedules) {
      expect(schedule.condition).toEqual({
        type: 'state',
        entity: 'virtual_switch',
        entity_id: PRESENCE_FLAG,
        state: 'is_on',
      });
    }
  });

  it('gives the flag a catch-up action for being armed after dusk', () => {
    const { virtualSwitch } = build();
    const actions = virtualSwitch.actions as Record<string, Record<string, unknown>[]>;
    expect(actions.on_turn_on[0]).toMatchObject({
      boneio_output: 'out_living',
      action_output: 'ON',
      conditions: {
        mode: 'and',
        list: [
          { type: 'sun', after: 'civil_dusk' },
          { type: 'time', before: '23:10' },
        ],
      },
    });
  });

  it('turns every light off when the flag goes off', () => {
    const { virtualSwitch } = build();
    const actions = virtualSwitch.actions as Record<string, Record<string, unknown>[]>;
    expect(actions.on_turn_off.map((a) => a.boneio_output)).toEqual(['out_living', 'out_bedroom']);
  });

  it('generates nothing but the flag when no light was picked', () => {
    // And the flag gets no actions either — one pointing at `undefined` would
    // be written to config.yaml and rejected on load.
    const { schedules, preview, virtualSwitch } = build({ lights: [] });
    expect(schedules).toEqual([]);
    expect(preview).toEqual([]);
    expect(virtualSwitch.actions).toEqual({ on_turn_on: [], on_turn_off: [] });
  });

  it('previews the evening it describes', () => {
    expect(build().preview).toEqual([
      { at: '~21:10', label: 'out_living' },
      { at: '~22:10', label: 'out_bedroom' },
      { at: '23:10', label: 'off' },
    ]);
  });

  it('wraps a bedtime early enough to push a step past midnight', () => {
    const { schedules } = build({ endsAt: '00:30', lights: ['a'] });
    expect(schedules[0].trigger).toMatchObject({ latest: '22:30' });
  });
});

describe('mergeGenerated', () => {
  it('replaces an earlier run and keeps everything else in order', () => {
    const existing = [
      { id: 'my_morning' },
      { id: 'presence_step_1' },
      { id: 'my_covers' },
      { id: 'presence_off' },
    ];
    const result = mergeGenerated(existing, [{ id: 'presence_step_1' }]);
    expect(result.map((e) => e.id)).toEqual(['my_morning', 'my_covers', 'presence_step_1']);
  });

  it('adds to a section that has none yet', () => {
    expect(mergeGenerated([{ id: 'mine' }], [{ id: 'presence_off' }]).map((e) => e.id))
      .toEqual(['mine', 'presence_off']);
  });
});

describe('isGenerated', () => {
  it('recognises only the wizard’s own ids', () => {
    expect(isGenerated({ id: 'presence_step_1' })).toBe(true);
    expect(isGenerated({ id: 'my_presence_thing' })).toBe(false);
    expect(isGenerated({})).toBe(false);
  });
});

describe('remote lights', () => {
  const remotes = { 'remote:esp_hall/lamp': { remote_device: 'esp_hall', output_id: 'lamp' } };

  it('switches a remote light with remote_output, never a local output action', () => {
    const { schedules, virtualSwitch } = build({ lights: ['out_living', 'remote:esp_hall/lamp'], remotes });
    const all = [
      ...schedules.flatMap((s) => s.actions as Record<string, unknown>[]),
      ...Object.values((virtualSwitch.actions as Record<string, Record<string, unknown>[]>)),
    ].flat() as Record<string, unknown>[];
    const remoteActions = all.filter((a) => a.action === 'remote_output');

    expect(remoteActions.length).toBeGreaterThan(0);
    for (const action of remoteActions) {
      expect(action).toMatchObject({ remote_device: 'esp_hall', output_id: 'lamp' });
      expect(action).not.toHaveProperty('boneio_output');
    }
    expect(all.some((a) => a.boneio_output === 'remote:esp_hall/lamp')).toBe(false);
  });
});
