import { describe, expect, it } from 'vitest';
import { keepPolling } from './proxySwitchPolling';

describe('keepPolling', () => {
  it('goes on through a failed read while a switch was running', () => {
    expect(keepPolling(null, true, false)).toBe(true);
  });
  it('goes on through a failed read right after the admin started one', () => {
    expect(keepPolling(null, false, true)).toBe(true);
  });
  it('stops on a failed read when nothing was running', () => {
    expect(keepPolling(null, false, false)).toBe(false);
  });
  it('follows the state on a good read', () => {
    expect(keepPolling({ switch: { running: true } }, false, false)).toBe(true);
    expect(keepPolling({ switch: { running: false } }, true, true)).toBe(false);
    expect(keepPolling({ switch: null }, true, true)).toBe(false);
  });
});
