/**
 * A failed read of /api/config used to resolve to an empty object. Settings
 * then drew every form with its defaults, and a save replaced the section with
 * them: a busy controller lost `web.expose: proxy` that way.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const get = vi.fn();

vi.mock('@/api/axios', () => ({
  default: { get: (...args: unknown[]) => get(...args) },
}));

import { fetchConfig, invalidateConfigCache } from '../configCache';

beforeEach(() => {
  get.mockReset();
  get.mockRejectedValue(new Error('timeout of 30000ms exceeded'));
  invalidateConfigCache();
});

describe('fetchConfig', () => {
  it('rejects when the configuration cannot be read', async () => {
    await expect(fetchConfig()).rejects.toThrow('timeout');
  });

  it('waits longer than the default 5 s for it', async () => {
    get.mockResolvedValue({ data: { config: { web: { expose: 'proxy' } } } });
    invalidateConfigCache();
    await expect(fetchConfig()).resolves.toEqual({ config: { web: { expose: 'proxy' } } });
    expect(get).toHaveBeenCalledWith('/api/config', { timeout: 30_000 });
  });
});
