/**
 * The reason the login screen gives for a sign-out.
 *
 * What matters is precedence: the 401 that says why arrives together with
 * others that do not, and those must not wipe it out.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { clearSignoutReason, readSignoutReason, rememberSignoutReason } from '../signoutReason';

class MemoryStorage {
  private data = new Map<string, string>();
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
}

beforeEach(() => {
  (globalThis as { sessionStorage?: unknown }).sessionStorage = new MemoryStorage();
});

describe('signoutReason', () => {
  it('keeps the reason a 401 gave', () => {
    rememberSignoutReason('session_locked');
    expect(readSignoutReason()).toBe('session_locked');
  });

  it('is not overwritten by the code-less 401s that follow', () => {
    rememberSignoutReason('session_locked');
    rememberSignoutReason(undefined);
    rememberSignoutReason('No authorization header');
    expect(readSignoutReason()).toBe('session_locked');
  });

  it('ignores codes it has nothing to say about', () => {
    rememberSignoutReason('forbidden');
    expect(readSignoutReason()).toBeNull();
  });

  it('reads the same reason twice until it is cleared', () => {
    rememberSignoutReason('session_revoked');
    expect(readSignoutReason()).toBe('session_revoked');
    expect(readSignoutReason()).toBe('session_revoked');
    clearSignoutReason();
    expect(readSignoutReason()).toBeNull();
  });

  it('survives storage being unavailable', () => {
    (globalThis as { sessionStorage?: unknown }).sessionStorage = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
      removeItem: () => {
        throw new Error('blocked');
      },
    };
    expect(() => rememberSignoutReason('session_locked')).not.toThrow();
    expect(readSignoutReason()).toBeNull();
    expect(() => clearSignoutReason()).not.toThrow();
  });
});
