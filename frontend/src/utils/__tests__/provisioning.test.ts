import { describe, it, expect } from 'vitest';
import {
  provisioningHintKey,
  readProvisioningHint,
  writeProvisioningHint,
  type HintStorage,
} from '../provisioning';

/** Storage stand-in; `failing` models a browser that blocks site data. */
function fakeStorage(initial: Record<string, string> = {}, failing = false): HintStorage {
  const map = new Map(Object.entries(initial));
  return {
    getItem(key) {
      if (failing) throw new Error('access denied');
      return map.get(key) ?? null;
    },
    setItem(key, value) {
      if (failing) throw new Error('access denied');
      map.set(key, value);
    },
  };
}

describe('provisioningHintKey', () => {
  it('uses one key for a device reached directly', () => {
    expect(provisioningHintKey(undefined)).toBe('boneio-provisioned');
    expect(provisioningHintKey('')).toBe('boneio-provisioned');
  });

  it('scopes the key per device behind HA ingress', () => {
    // Several controllers share the browser origin there, so an unscoped key
    // would let the first one answer for all of them.
    expect(provisioningHintKey('/api/hassio_ingress/abc/proxy/0')).toBe(
      'boneio-provisioned-proxy-0',
    );
    expect(provisioningHintKey('/api/hassio_ingress/abc/proxy/1/')).toBe(
      'boneio-provisioned-proxy-1',
    );
  });
});

describe('readProvisioningHint', () => {
  it('is true only for a device seen provisioned', () => {
    expect(readProvisioningHint(fakeStorage({ 'boneio-provisioned': '1' }), undefined)).toBe(true);
    expect(readProvisioningHint(fakeStorage({ 'boneio-provisioned': '0' }), undefined)).toBe(false);
  });

  it('is false when nothing is known', () => {
    expect(readProvisioningHint(fakeStorage(), undefined)).toBe(false);
    expect(readProvisioningHint(undefined, undefined)).toBe(false);
  });

  it('is false when the browser refuses storage', () => {
    expect(readProvisioningHint(fakeStorage({}, true), undefined)).toBe(false);
  });

  it('does not read another device’s hint', () => {
    const storage = fakeStorage({ 'boneio-provisioned-proxy-0': '1' });
    expect(readProvisioningHint(storage, '/api/hassio_ingress/abc/proxy/1')).toBe(false);
  });
});

describe('writeProvisioningHint', () => {
  it('round-trips both answers', () => {
    const storage = fakeStorage();

    writeProvisioningHint(storage, undefined, false);
    expect(readProvisioningHint(storage, undefined)).toBe(true);

    // A device that was wiped back to unprovisioned must clear the hint.
    writeProvisioningHint(storage, undefined, true);
    expect(readProvisioningHint(storage, undefined)).toBe(false);
  });

  it('writes under the scoped key', () => {
    const storage = fakeStorage();
    writeProvisioningHint(storage, '/api/hassio_ingress/abc/proxy/2', false);
    expect(readProvisioningHint(storage, '/api/hassio_ingress/abc/proxy/2')).toBe(true);
    expect(readProvisioningHint(storage, undefined)).toBe(false);
  });

  it('survives a browser that refuses storage', () => {
    expect(() => writeProvisioningHint(fakeStorage({}, true), undefined, false)).not.toThrow();
    expect(() => writeProvisioningHint(undefined, undefined, false)).not.toThrow();
  });
});
