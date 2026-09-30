// @vitest-environment jsdom
/**
 * The broker's TLS card: what it lets people do in each state, and what it
 * asks before restarting the broker under them.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BrokerTlsCard, { type BrokerState } from './BrokerTlsCard';

const get = vi.fn();
const post = vi.fn();
const put = vi.fn();

vi.mock('@/api/axios', () => ({
  default: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
    put: (...args: unknown[]) => put(...args),
    delete: vi.fn(),
  },
}));

vi.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const base: BrokerState = {
  supported: true,
  mode: 'off',
  active: true,
  has_certificate: false,
  certificate: null,
  tls_port: 8883,
  reached_by: ['boneio', 'boneio.local', '192.168.1.50'],
  app: { host: 'localhost', port: 1883, uses_local_broker: true, tls: false, blocks_required: false },
};

const withCert: Partial<BrokerState> = {
  has_certificate: true,
  certificate: {
    subject: 'CN=boneio.local',
    issuer: 'O=boneIO,CN=boneio MQTT CA',
    not_after: '2036-09-30T00:00:00+00:00',
    days_left: 3650,
    names: ['boneio.local', '192.168.1.50'],
    uncovered: [],
    ca_available: true,
  },
};

function serve(state: Partial<BrokerState>) {
  get.mockImplementation((url: string) =>
    url === '/api/mqtt-tls/broker' ? Promise.resolve({ data: { ...base, ...state } }) : Promise.reject(new Error(url)),
  );
}

const modeCard = (name: string) => screen.getByText(name).closest('[class*="transition-all"]') as HTMLElement;

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  put.mockReset();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('BrokerTlsCard', () => {
  it('says what to do on a controller whose helper predates this', async () => {
    serve({ supported: false });
    render(<BrokerTlsCard />);
    expect(await screen.findByText('mqtt_tls.broker.unsupported')).toBeTruthy();
    expect((screen.getByText('mqtt_tls.broker.generate').closest('button') as HTMLButtonElement).disabled).toBe(true);
  });

  it('refuses to manage a hand-edited configuration', async () => {
    serve({ mode: 'custom', ...withCert });
    render(<BrokerTlsCard />);
    expect(await screen.findByText('mqtt_tls.broker.custom')).toBeTruthy();
  });

  it('TLS needs a certificate before it can be turned on', async () => {
    serve({});
    render(<BrokerTlsCard />);
    await screen.findByText('mqtt_tls.broker.mode_optional');
    expect(screen.getAllByText('mqtt_tls.broker.needs_certificate').length).toBe(1);
    expect((screen.getByText('mqtt_tls.broker.mode_optional').closest('button') as HTMLButtonElement | null)?.disabled ?? true).toBe(true);
  });

  it('explains why TLS-only would cut boneIO off', async () => {
    serve({ ...withCert, app: { ...base.app, host: '192.168.1.50', blocks_required: true } });
    render(<BrokerTlsCard />);
    expect(await screen.findByText('mqtt_tls.broker.blocked_by_app')).toBeTruthy();
  });

  it('switching mode asks first, then tells the helper', async () => {
    serve(withCert);
    put.mockResolvedValue({ data: { mode: 'optional' } });
    render(<BrokerTlsCard />);
    await screen.findByText('mqtt_tls.broker.mode_optional');

    await userEvent.click(screen.getByText('mqtt_tls.broker.mode_optional'));
    expect(window.confirm).toHaveBeenCalledWith('mqtt_tls.broker.confirm_optional');
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith('/api/mqtt-tls/broker/mode', { mode: 'optional' }, expect.anything()),
    );
    expect(modeCard('mqtt_tls.broker.mode_optional')).toBeTruthy();
  });

  it('declining the question changes nothing', async () => {
    serve(withCert);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<BrokerTlsCard />);
    await screen.findByText('mqtt_tls.broker.mode_required');
    await userEvent.click(screen.getByText('mqtt_tls.broker.mode_required'));
    expect(put).not.toHaveBeenCalled();
  });

  it('a new certificate over an old one warns that clients need the new CA', async () => {
    serve(withCert);
    post.mockResolvedValue({ data: {} });
    render(<BrokerTlsCard />);
    await userEvent.click(await screen.findByText('mqtt_tls.broker.generate'));
    expect(window.confirm).toHaveBeenCalledWith('mqtt_tls.broker.generate_confirm');
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/mqtt-tls/broker/generate', null, expect.anything()));
    expect(await screen.findByText('mqtt_tls.broker.generated')).toBeTruthy();
  });

  it("shows the helper's refusal as it was said", async () => {
    serve(withCert);
    put.mockRejectedValue({ response: { data: { detail: 'the broker did not start with the new TLS settings' } } });
    render(<BrokerTlsCard />);
    await userEvent.click(await screen.findByText('mqtt_tls.broker.mode_required'));
    expect(await screen.findByText('the broker did not start with the new TLS settings')).toBeTruthy();
  });

  it('offers the CA only when the chain carries one', async () => {
    serve(withCert);
    render(<BrokerTlsCard />);
    expect(await screen.findByText('mqtt_tls.broker.download_ca')).toBeTruthy();
    cleanup();
    serve({ ...withCert, certificate: { ...withCert.certificate!, ca_available: false } });
    render(<BrokerTlsCard />);
    await screen.findByText('mqtt_tls.broker.generate');
    expect(screen.queryByText('mqtt_tls.broker.download_ca')).toBeNull();
  });
});
