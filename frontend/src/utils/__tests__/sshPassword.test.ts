import { describe, it, expect } from 'vitest';
import { sshCardMode } from '../sshPassword';

describe('sshCardMode', () => {
  it('offers the form where there is a current password to give', () => {
    expect(sshCardMode('set', true)).toBe('form');
    expect(sshCardMode('shipped', true)).toBe('form');
  });

  it('names the pending migration instead of a form that can only fail', () => {
    expect(sshCardMode('set', false)).toBe('outdated');
    expect(sshCardMode('shipped', false)).toBe('outdated');
  });

  it('never offers the form without a password to check', () => {
    // Locked and empty are the wizard's, once, and then the flasher's.
    for (const supported of [true, false]) {
      expect(sshCardMode('locked', supported)).toBe('locked');
      expect(sshCardMode('empty', supported)).toBe('empty');
    }
  });

  it('does not guess when the helper could not say', () => {
    expect(sshCardMode(null, true)).toBe('unknown');
    expect(sshCardMode('unknown', true)).toBe('unknown');
  });
});
