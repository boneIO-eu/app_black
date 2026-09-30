// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook } from '@testing-library/react';
import { useGroupByArea } from '../useGroupByArea';

// Node's own experimental `localStorage` global shadows jsdom's and is
// undefined without --localstorage-file, so the test brings a plain one.
beforeEach(() => {
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, String(value)),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('useGroupByArea', () => {
  it('is off by default', () => {
    const { result } = renderHook(() => useGroupByArea('k', true));
    expect(result.current[0]).toBe(false);
  });

  it('remembers the choice per key', () => {
    const { result } = renderHook(() => useGroupByArea('k', true));
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
    expect(localStorage.getItem('k')).toBe('true');

    const other = renderHook(() => useGroupByArea('other', true));
    expect(other.result.current[0]).toBe(false);
  });

  it('stays off with no areas configured, even when it was left on', () => {
    localStorage.setItem('k', 'true');
    const { result, rerender } = renderHook(({ hasAreas }) => useGroupByArea('k', hasAreas), {
      initialProps: { hasAreas: false },
    });
    expect(result.current[0]).toBe(false);

    // The areas arrive with the config: the remembered choice applies then.
    rerender({ hasAreas: true });
    expect(result.current[0]).toBe(true);
  });
});
