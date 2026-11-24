import { describe, it, expect } from 'vitest';
import { busIdsOf, withExplicitBus } from './modbusBus';

describe('withExplicitBus', () => {
  it('leaves a device alone when there is one bus', () => {
    expect(withExplicitBus({ address: 1 }, ['a'])).toEqual({ address: 1 });
  });

  it('names the first bus when there are several', () => {
    expect(withExplicitBus({ address: 1 }, ['a', 'b'])).toEqual({ address: 1, bus: 'a' });
  });

  it('keeps a bus the device already names', () => {
    expect(withExplicitBus({ address: 1, bus: 'b' }, ['a', 'b'])).toEqual({ address: 1, bus: 'b' });
  });
});

describe('busIdsOf', () => {
  it('lists the ids of a modbus section in order', () => {
    expect(busIdsOf([{ id: 'rs485', port: 'uart4' }, { id: 'usb', port: '/dev/ttyUSB0' }])).toEqual(['rs485', 'usb']);
  });

  it('is empty for a missing or malformed section', () => {
    expect(busIdsOf(undefined)).toEqual([]);
    expect(busIdsOf({ uart: 'uart4' })).toEqual([]);
    expect(busIdsOf([{ port: 'uart4' }, null])).toEqual([]);
  });
});
