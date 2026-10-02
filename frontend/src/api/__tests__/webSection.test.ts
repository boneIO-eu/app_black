/**
 * PUT /api/config/web replaces the whole section. Both callers that change one
 * setting in it — the onboarding PWA step and "move behind the proxy" — read
 * the section a level too high in the GET response, merged into nothing, and
 * saved a section holding only their own key. A fresh controller lost
 * `expose: proxy` that way the moment PWA was switched on.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const get = vi.fn();
const put = vi.fn();

vi.mock('@/api/axios', () => ({
  default: {
    get: (...args: unknown[]) => get(...args),
    put: (...args: unknown[]) => put(...args),
  },
}));

import { updateWebSection } from '../webSection';

const STORED = {
  port: 8090,
  proxy_port: 8443,
  expose: 'proxy',
  security: { frame_ancestors: "'self'" },
};

beforeEach(() => {
  get.mockReset();
  put.mockReset();
  // The shape GET /api/config really answers with: sections under `config`.
  get.mockResolvedValue({ data: { config: { web: STORED, mqtt: { host: 'x' } } } });
  put.mockResolvedValue({ data: { status: 'success', cloud: 'started' } });
});

describe('updateWebSection', () => {
  it('keeps every stored key when switching PWA on', async () => {
    await updateWebSection((web) => ({ ...web, cloud: { enabled: true } }));

    expect(put).toHaveBeenCalledWith(
      '/api/config/web',
      { ...STORED, cloud: { enabled: true } },
      undefined,
    );
  });

  it('keeps cloud when moving behind the proxy', async () => {
    // Dropping `cloud` here is read by the backend as PWA switched off.
    get.mockResolvedValue({
      data: { config: { web: { port: 8090, cloud: { enabled: true } } } },
    });

    await updateWebSection((web) => ({ ...web, expose: 'proxy' }), { timeout: 30000 });

    expect(put).toHaveBeenCalledWith(
      '/api/config/web',
      { port: 8090, cloud: { enabled: true }, expose: 'proxy' },
      { timeout: 30000 },
    );
  });

  it('starts from an empty section on a config without one', async () => {
    get.mockResolvedValue({ data: { config: {} } });

    await updateWebSection((web) => ({ ...web, expose: 'proxy' }));

    expect(put).toHaveBeenCalledWith('/api/config/web', { expose: 'proxy' }, undefined);
  });

  it('returns what the save answered', async () => {
    await expect(
      updateWebSection((web) => ({ ...web, cloud: { enabled: true } })),
    ).resolves.toEqual({ status: 'success', cloud: 'started' });
  });
});
