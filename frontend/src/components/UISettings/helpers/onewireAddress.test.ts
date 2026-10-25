import { describe, expect, it } from 'vitest';
import { esphomeAddress, kernelAddress } from './onewireAddress';

// The same pairs as tests/unit/core/test_onewire_address.py.
const PAIRS = [
  ['28-000000053f33', '0xc0000000053f3328'],
  ['28-02131dda9aaa', '0xc202131dda9aaa28'],
];

describe('onewireAddress', () => {
  it.each(PAIRS)('%s is %s', (kernel, esphome) => {
    expect(kernelAddress(esphome)).toBe(kernel);
    expect(esphomeAddress(kernel)).toBe(esphome);
    expect(esphomeAddress(esphome)).toBe(esphome);
  });

  it('takes upper case and a bare serial', () => {
    expect(kernelAddress('0XC202131DDA9AAA28')).toBe('28-02131dda9aaa');
    expect(kernelAddress('02131dda9aaa')).toBe('28-02131dda9aaa');
  });

  it('refuses a wrong CRC and garbage', () => {
    expect(kernelAddress('0xc302131dda9aaa28')).toBeNull();
    expect(esphomeAddress('dallas')).toBeNull();
  });
});
