/**
 * The schema is 434 KB of static, build-time JSON. It was re-fetched on every
 * entry into Settings, with `Cache-Control: no-store` so the browser could not
 * even keep a copy to revalidate — about a second on a BeagleBone, each time,
 * for a file that had not changed.
 *
 * These tests pin the part that matters: how many requests actually go out.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const get = vi.fn();

vi.mock('@/api/axios', () => ({
  default: { get: (...args: unknown[]) => get(...args) },
}));

import { fetchSchema, prefetchSchema, resetSchemaCache } from '../schemaCache';

const SCHEMA = { properties: { output: { type: 'array' } } };

beforeEach(() => {
  resetSchemaCache();
  get.mockReset();
  get.mockResolvedValue({ data: SCHEMA });
});

afterEach(() => {
  resetSchemaCache();
});

describe('fetchSchema', () => {
  it('returns the parsed schema', async () => {
    await expect(fetchSchema()).resolves.toEqual(SCHEMA);
  });

  it('asks the server once, however many times it is called', async () => {
    // Entering Settings, leaving for Inputs, coming back. Three mounts, one
    // request — that is the whole fix.
    await fetchSchema();
    await fetchSchema();
    await fetchSchema();
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('shares one request between callers that arrive together', async () => {
    // ConfigEditor and UISettings can both ask before either has an answer.
    let release: (value: unknown) => void = () => {};
    get.mockReturnValueOnce(new Promise((resolve) => { release = resolve; }));

    const first = fetchSchema();
    const second = fetchSchema();
    release({ data: SCHEMA });

    expect(await first).toEqual(SCHEMA);
    expect(await second).toEqual(SCHEMA);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('does not send a header that forbids caching', async () => {
    // The old call passed Cache-Control: no-store, which is what turned a
    // cheap 304 into a full 434 KB body on every visit.
    await fetchSchema();
    const [, options] = get.mock.calls[0] as [string, Record<string, any>?];
    const headers = options?.headers ?? {};
    expect(JSON.stringify(headers)).not.toContain('no-store');
  });

  it('retries after a failure instead of caching it', async () => {
    // A restart mid-request should not poison Settings until the next reload.
    get.mockRejectedValueOnce(new Error('controller restarting'));
    await expect(fetchSchema()).rejects.toThrow('controller restarting');

    get.mockResolvedValue({ data: SCHEMA });
    await expect(fetchSchema()).resolves.toEqual(SCHEMA);
    expect(get).toHaveBeenCalledTimes(2);
  });
});

describe('prefetchSchema', () => {
  it('warms the cache so the next caller pays nothing', async () => {
    prefetchSchema();
    await fetchSchema();
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('swallows a failure rather than surfacing an unhandled rejection', async () => {
    get.mockRejectedValue(new Error('offline'));
    expect(() => prefetchSchema()).not.toThrow();
    await Promise.resolve();
  });
});
