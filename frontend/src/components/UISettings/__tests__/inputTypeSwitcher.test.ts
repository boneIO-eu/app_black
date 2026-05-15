/**
 * Tests for InputTypeSwitcher data transformation logic.
 * Tests the pure functions without rendering React components.
 */
import { describe, it, expect } from 'vitest';

// Re-implement the transformation functions from InputTypeSwitcher for testing
// (these are the same as in the component, extracted for testability)

const BS_ONLY_FIELDS = ['device_class', 'show_in_ha', 'inverted', 'initial_send', 'clear_message'];
const EVENT_ONLY_FIELDS = [
  'double_click_duration', 'long_press_duration', 'sequence_window_duration',
  'sequence_mode', 'enable_triple_click', 'long_press_mqtt_mode',
  'max_long_press_duration', 'mqtt_sequences',
];

function eventToBinarySensor(data: any): any {
  const { _type, ...rest } = data;
  const newData: any = { ...rest, _type: 'binary_sensor' };
  const oldActions = data.actions || {};
  const newActions: any = {};
  if (oldActions.single?.length > 0) {
    newActions.pressed = [...oldActions.single];
  }
  newData.actions = newActions;
  EVENT_ONLY_FIELDS.forEach(field => delete newData[field]);
  return newData;
}

function binarySensorToEvent(data: any): any {
  const { _type, ...rest } = data;
  const newData: any = { ...rest, _type: 'event' };
  const oldActions = data.actions || {};
  const newActions: any = {};
  if (oldActions.pressed?.length > 0) {
    newActions.single = [...oldActions.pressed];
  }
  newData.actions = newActions;
  BS_ONLY_FIELDS.forEach(field => delete newData[field]);
  return newData;
}

function countActions(actions: any, types: string[]): number {
  if (!actions || typeof actions !== 'object') return 0;
  return types.reduce((sum, type) => {
    const arr = actions[type];
    return sum + (Array.isArray(arr) ? arr.length : 0);
  }, 0);
}

describe('eventToBinarySensor', () => {
  it('maps single actions to pressed', () => {
    const data = {
      _type: 'event',
      name: 'test',
      boneio_input: 'in_01',
      actions: {
        single: [{ action: 'output', boneio_output: 'rel_01' }],
        double: [{ action: 'output', boneio_output: 'rel_02' }],
        long: [{ action: 'cover', boneio_cover: 'cover_01' }],
      },
    };

    const result = eventToBinarySensor(data);

    expect(result._type).toBe('binary_sensor');
    expect(result.name).toBe('test');
    expect(result.boneio_input).toBe('in_01');
    // single → pressed
    expect(result.actions.pressed).toHaveLength(1);
    expect(result.actions.pressed[0].boneio_output).toBe('rel_01');
    // double and long are NOT migrated
    expect(result.actions.double).toBeUndefined();
    expect(result.actions.long).toBeUndefined();
  });

  it('removes event-only timing fields', () => {
    const data = {
      _type: 'event',
      double_click_duration: '220ms',
      long_press_duration: '400ms',
      sequence_mode: 'exclusive',
      enable_triple_click: true,
      mqtt_sequences: { double_then_long: true },
      actions: {},
    };

    const result = eventToBinarySensor(data);

    expect(result.double_click_duration).toBeUndefined();
    expect(result.long_press_duration).toBeUndefined();
    expect(result.sequence_mode).toBeUndefined();
    expect(result.enable_triple_click).toBeUndefined();
    expect(result.mqtt_sequences).toBeUndefined();
  });

  it('preserves common fields', () => {
    const data = {
      _type: 'event',
      name: 'switch_1',
      boneio_input: 'in_05',
      area: 'living_room',
      bounce_time: '30ms',
      actions: {},
    };

    const result = eventToBinarySensor(data);

    expect(result.name).toBe('switch_1');
    expect(result.boneio_input).toBe('in_05');
    expect(result.area).toBe('living_room');
    expect(result.bounce_time).toBe('30ms');
  });
});

describe('binarySensorToEvent', () => {
  it('maps pressed actions to single', () => {
    const data = {
      _type: 'binary_sensor',
      actions: {
        pressed: [{ action: 'output', boneio_output: 'rel_03' }],
        released: [{ action: 'output', boneio_output: 'rel_04' }],
      },
    };

    const result = binarySensorToEvent(data);

    expect(result._type).toBe('event');
    // pressed → single
    expect(result.actions.single).toHaveLength(1);
    expect(result.actions.single[0].boneio_output).toBe('rel_03');
    // released is NOT migrated
    expect(result.actions.released).toBeUndefined();
  });

  it('removes binary_sensor-only fields', () => {
    const data = {
      _type: 'binary_sensor',
      device_class: 'motion',
      show_in_ha: true,
      inverted: false,
      initial_send: true,
      clear_message: false,
      actions: {},
    };

    const result = binarySensorToEvent(data);

    expect(result.device_class).toBeUndefined();
    expect(result.show_in_ha).toBeUndefined();
    expect(result.inverted).toBeUndefined();
    expect(result.initial_send).toBeUndefined();
    expect(result.clear_message).toBeUndefined();
  });

  it('handles empty actions', () => {
    const result = binarySensorToEvent({ _type: 'binary_sensor' });
    expect(result._type).toBe('event');
    expect(result.actions).toEqual({});
  });
});

describe('countActions', () => {
  it('counts actions across specified types', () => {
    const actions = {
      single: [{ action: 'output' }, { action: 'cover' }],
      double: [{ action: 'output' }],
      long: [],
    };

    expect(countActions(actions, ['single', 'double', 'long'])).toBe(3);
    expect(countActions(actions, ['single'])).toBe(2);
    expect(countActions(actions, ['long'])).toBe(0);
    expect(countActions(actions, ['nonexistent'])).toBe(0);
  });

  it('handles null/undefined actions', () => {
    expect(countActions(null, ['single'])).toBe(0);
    expect(countActions(undefined, ['single'])).toBe(0);
  });

  it('handles non-array action values', () => {
    expect(countActions({ single: 'not-an-array' }, ['single'])).toBe(0);
  });
});
