import { describe, it, expect } from 'vitest';
import { resolveId, slugifyId } from './slugifyId';

/** These cases are the same ones in tests/unit/core/test_naming.py. The two
 *  implementations have to agree, or the panel shows an identifier the device
 *  will not use. */
describe('slugifyId', () => {
  it.each([
    ['Nie ma nas w domu', 'nie_ma_nas_w_domu'],
    ['Evening mode', 'evening_mode'],
    ['  Salon  ', 'salon'],
    ['Salon / Piętro 1', 'salon_pietro_1'],
    ['OUT-11', 'out_11'],
    ['a---b', 'a_b'],
    ['!!!', ''],
    ['', ''],
  ])('%s → %s', (name, expected) => {
    expect(slugifyId(name)).toBe(expected);
  });

  it.each([
    ['Wyjście główne', 'wyjscie_glowne'],
    ['Łazienka', 'lazienka'],
    ['Zażółć gęślą jaźń', 'zazolc_gesla_jazn'],
    ['Küche', 'kuche'],
    ['Straße', 'strasse'],
    ['Sønder', 'sonder'],
  ])('folds accents: %s → %s', (name, expected) => {
    expect(slugifyId(name)).toBe(expected);
  });

  it('never leaves anything an MQTT topic parses', () => {
    for (const name of ['a/b', 'a+b', 'a#b', 'a b', 'Ą/Ż']) {
      expect(slugifyId(name)).not.toMatch(/[/+# ]/);
    }
  });
});

describe('resolveId', () => {
  it('prefers an explicit id', () => {
    expect(resolveId({ id: 'away', name: 'Nie ma nas w domu' })).toBe('away');
  });

  it('falls back to the name', () => {
    expect(resolveId({ name: 'Nie ma nas w domu' })).toBe('nie_ma_nas_w_domu');
  });

  it('treats a blank id as none', () => {
    expect(resolveId({ id: '   ', name: 'Evening' })).toBe('evening');
  });

  it('has nothing to give when the entry has neither', () => {
    expect(resolveId({})).toBe('');
  });
});
