// @vitest-environment jsdom
/**
 * The TLS block of the MQTT page: what it writes into `mqtt.tls` (and the
 * port) for each choice, and that uploads land as paths in the form.
 */
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MqttTlsSettings, { type MqttTlsConfig } from './MqttTlsSettings';

const get = vi.fn();
const post = vi.fn();

vi.mock('@/api/axios', () => ({
  default: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
  },
}));

vi.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const storedCa = {
  path: 'certs/mqtt-ca.pem',
  subject: 'CN=My CA',
  issuer: 'CN=My CA',
  not_after: '2036-01-01T00:00:00+00:00',
  names: [],
  count: 1,
};

function answer(
  files: Record<string, unknown> = { ca: null, client: null },
  tlsError: string | null = null,
  link: { connected?: boolean; tls_in_use?: boolean } = {},
) {
  get.mockResolvedValue({
    data: { files, tls_error: tlsError, connected: link.connected ?? false, tls_in_use: link.tls_in_use ?? false },
  });
}

/** Holds the section and the port the way MqttForm does. */
function Harness({ tls, port, spy }: { tls?: MqttTlsConfig; port?: number; spy: (s: { tls?: MqttTlsConfig; port?: number }) => void }) {
  const [state, setState] = useState<{ tls?: MqttTlsConfig; port?: number }>({ tls, port });
  return (
    <MqttTlsSettings
      tls={state.tls}
      port={state.port}
      onChange={(next, nextPort) => {
        const updated = { tls: next, port: nextPort ?? state.port };
        setState(updated);
        spy(updated);
      }}
    />
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
});
afterEach(cleanup);

describe('MqttTlsSettings', () => {
  it('turning TLS on moves the default port to 8883, and back', async () => {
    answer();
    const spy = vi.fn();
    render(<Harness port={1883} spy={spy} />);
    const toggle = screen.getByRole('checkbox');

    await userEvent.click(toggle);
    expect(spy).toHaveBeenLastCalledWith({ tls: { enabled: true }, port: 8883 });

    await userEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(spy).toHaveBeenLastCalledWith({ tls: { enabled: false }, port: 1883 });
  });

  it('a port of its own is left alone', async () => {
    answer();
    const spy = vi.fn();
    render(<Harness port={18883} spy={spy} />);
    await userEvent.click(screen.getByRole('checkbox'));
    expect(spy).toHaveBeenLastCalledWith({ tls: { enabled: true }, port: 18883 });
  });

  it('choosing my own CA points at the stored one', async () => {
    answer({ ca: storedCa, client: null });
    const spy = vi.fn();
    render(<Harness tls={{ enabled: true }} port={8883} spy={spy} />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    await waitFor(() => screen.getByRole('combobox'));

    await userEvent.selectOptions(screen.getByRole('combobox'), 'custom');
    expect(spy).toHaveBeenLastCalledWith({
      tls: { enabled: true, ca_certs: 'certs/mqtt-ca.pem' },
      port: 8883,
    });
    expect(screen.getByText('CN=My CA')).toBeTruthy();
  });

  it('insecure drops the CA and says what it costs', async () => {
    answer();
    const spy = vi.fn();
    render(<Harness tls={{ enabled: true, ca_certs: 'certs/mqtt-ca.pem' }} port={8883} spy={spy} />);

    await userEvent.selectOptions(screen.getByRole('combobox'), 'insecure');
    expect(spy).toHaveBeenLastCalledWith({ tls: { enabled: true, insecure: true }, port: 8883 });
    expect(screen.getByText('mqtt_tls.insecure_warning')).toBeTruthy();
  });

  it('an uploaded CA lands in the form as its path', async () => {
    answer();
    post.mockResolvedValue({ data: { stored: storedCa } });
    const spy = vi.fn();
    const { container } = render(<Harness tls={{ enabled: true, ca_certs: 'x.pem' }} port={8883} spy={spy} />);

    const input = container.querySelector('input[type=file]') as HTMLInputElement;
    await userEvent.upload(input, new File(['pem'], 'ca.crt'));
    await userEvent.click(screen.getByText('mqtt_tls.upload'));

    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/mqtt-tls/client/ca', expect.any(FormData), expect.anything()));
    await waitFor(() =>
      expect(spy).toHaveBeenLastCalledWith({ tls: { enabled: true, ca_certs: 'certs/mqtt-ca.pem' }, port: 8883 }),
    );
  });

  it('shows why the running connection cannot use TLS', async () => {
    answer({ ca: null, client: null }, 'The CA certificate x does not exist.');
    render(<Harness tls={{ enabled: true }} port={8883} spy={vi.fn()} />);
    expect(await screen.findByText('The CA certificate x does not exist.')).toBeTruthy();
  });

  it('follows the section when it changes from outside, e.g. Restore', async () => {
    answer();
    const onChange = vi.fn();
    const { rerender } = render(
      <MqttTlsSettings tls={{ enabled: true, ca_certs: 'certs/mqtt-ca.pem' }} port={8883} onChange={onChange} />,
    );
    const select = () => screen.getByRole('combobox') as HTMLSelectElement;
    expect(select().value).toBe('custom');

    rerender(<MqttTlsSettings tls={{ enabled: true, insecure: true }} port={8883} onChange={onChange} />);
    expect(select().value).toBe('insecure');

    rerender(<MqttTlsSettings tls={{ enabled: true }} port={8883} onChange={onChange} />);
    expect(select().value).toBe('system');
  });

  it('an unfinished "my own CA" is dropped by a Restore', async () => {
    answer();
    const onChange = vi.fn();
    const { rerender } = render(<MqttTlsSettings tls={{ enabled: true }} port={8883} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole('combobox'), 'custom');
    // Nothing stored, so nothing to write yet — but the choice is shown.
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('custom');

    rerender(<MqttTlsSettings tls={{ enabled: true, insecure: false }} port={8883} onChange={onChange} />);
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('system');
  });

  it('data arriving after mount turns the client certificate toggle on', () => {
    answer();
    const { rerender } = render(<MqttTlsSettings tls={undefined} port={1883} onChange={vi.fn()} />);
    rerender(
      <MqttTlsSettings
        tls={{ enabled: true, certfile: 'certs/mqtt-client.pem', keyfile: 'certs/mqtt-client.key' }}
        port={8883}
        onChange={vi.fn()}
      />,
    );
    const toggles = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(toggles.map((t) => t.checked)).toEqual([true, true]);
  });

  it('says when the running connection is encrypted', async () => {
    answer(undefined, null, { connected: true, tls_in_use: true });
    render(<Harness tls={{ enabled: true }} port={8883} spy={vi.fn()} />);
    expect(await screen.findByText('mqtt_tls.status_tls')).toBeTruthy();
  });

  it('says when TLS is chosen but the connection is still plain (not saved yet)', async () => {
    answer(undefined, null, { connected: true, tls_in_use: false });
    render(<Harness tls={{ enabled: true }} port={8883} spy={vi.fn()} />);
    expect(await screen.findByText('mqtt_tls.status_plain')).toBeTruthy();
  });

  it('says when there is no connection', async () => {
    answer(undefined, null, { connected: false, tls_in_use: true });
    render(<Harness tls={{ enabled: true }} port={8883} spy={vi.fn()} />);
    expect(await screen.findByText('mqtt_tls.status_disconnected')).toBeTruthy();
  });

  it('shows nothing but the switch while TLS is off', () => {
    answer();
    render(<Harness port={1883} spy={vi.fn()} />);
    expect(screen.queryByRole('combobox')).toBeNull();
  });
});
