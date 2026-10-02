// @vitest-environment jsdom
/**
 * Switching the PWA on recreates Caddy, the only way into a panel with
 * web.expose: proxy. The wizard used to reload straight into "the controller
 * is not answering" and leave the owner on the old address. It now waits for
 * the backend's `serving`, checks the new address from the browser, and only
 * then offers it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook } from '@testing-library/react';

const get = vi.fn();

vi.mock('@/api/axios', () => ({
  default: { get: (...args: unknown[]) => get(...args) },
}));

import { isCurrentOrigin, probeReachable, useCloudSwitch } from '../useCloudSwitch';

const URL_CLOUD = 'https://blk239bb2.black.boneio.app:8443';
const fetchMock = vi.fn();

/** Answers for successive polls; a string is a network failure. */
function polls(...answers: (object | 'down')[]) {
  for (const answer of answers) {
    if (answer === 'down') get.mockRejectedValueOnce(new Error('Network Error'));
    else get.mockResolvedValueOnce({ data: answer });
  }
}

/** Let the hook's loop take one more turn of its 3 s wait. */
async function tick(ms = 3_000) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  get.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('useCloudSwitch', () => {
  it('does nothing until registration is on', () => {
    const { result } = renderHook(() => useCloudSwitch(false));
    expect(result.current.phase).toBe('idle');
    expect(get).not.toHaveBeenCalled();
  });

  it('rides out the proxy being down and ends ready at the new address', async () => {
    polls(
      { serving: false, url: null },
      'down',
      'down',
      { serving: true, url: URL_CLOUD },
    );
    fetchMock.mockResolvedValue({ type: 'opaque' });

    const { result } = renderHook(() => useCloudSwitch(true));
    expect(result.current.phase).toBe('switching');

    await tick(0);
    await tick();
    await tick();
    expect(result.current.phase).toBe('switching');
    await tick();

    expect(result.current).toEqual({ phase: 'ready', url: URL_CLOUD, error: null });
    expect(fetchMock).toHaveBeenCalledWith(
      `${URL_CLOUD}/api/init`,
      expect.objectContaining({ mode: 'no-cors', credentials: 'omit' }),
    );
  });

  it('does not ask the browser about the name before Caddy serves it', async () => {
    // A lookup made too early can be cached as a failure for minutes.
    polls({ serving: false, url: URL_CLOUD }, { serving: false, url: URL_CLOUD });

    renderHook(() => useCloudSwitch(true));
    await tick(0);
    await tick();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reports a name this browser cannot reach instead of sending anybody there', async () => {
    polls({ serving: true, url: URL_CLOUD });
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    const { result } = renderHook(() => useCloudSwitch(true));
    await tick(0);
    for (let i = 0; i < 4; i++) await tick();

    expect(result.current).toEqual({ phase: 'unreachable', url: URL_CLOUD, error: null });
  });

  it('gives up after three minutes and passes the backend error on', async () => {
    get.mockResolvedValue({ data: { serving: false, url: null, last_error: 'DNS registration failed' } });

    const { result } = renderHook(() => useCloudSwitch(true));
    await tick(181_000);

    expect(result.current).toEqual({ phase: 'timeout', url: null, error: 'DNS registration failed' });
  });
});

describe('isCurrentOrigin', () => {
  it('compares origins, port included', () => {
    const here = { origin: 'https://blk239bb2.black.boneio.app:8443' };
    expect(isCurrentOrigin(URL_CLOUD, here)).toBe(true);
    expect(isCurrentOrigin(URL_CLOUD, { origin: 'https://192.168.50.133:8443' })).toBe(false);
    expect(isCurrentOrigin('not a url', here)).toBe(false);
  });
});

describe('probeReachable', () => {
  it('is false when the fetch never completes', async () => {
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        }),
    );
    const pending = probeReachable(URL_CLOUD, 1_000);
    await vi.advanceTimersByTimeAsync(1_000);
    await expect(pending).resolves.toBe(false);
  });
});
