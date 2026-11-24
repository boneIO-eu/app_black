import { describe, it, expect } from 'vitest';
import { busIdsOf, onSameBus, withExplicitBus } from './modbusBus';

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

describe('onSameBus', () => {
  const used = [
    { address: 1, bus: 'a' },
    { address: 1, bus: 'b' },
    { address: 2 },
  ];

  it('keeps only the entries on the chosen bus, a device naming none being on the first', () => {
    expect(onSameBus(used, 'a', ['a', 'b'])).toEqual([{ address: 1, bus: 'a' }, { address: 2 }]);
    expect(onSameBus(used, 'b', ['a', 'b'])).toEqual([{ address: 1, bus: 'b' }]);
    expect(onSameBus(used, undefined, ['a', 'b'])).toEqual([{ address: 1, bus: 'a' }, { address: 2 }]);
  });

  it('treats a null bus from the server like a missing one when there are no buses', () => {
    expect(onSameBus([{ address: 3, bus: null }, { address: 4 }], undefined, [])).toHaveLength(2);
  });
});
