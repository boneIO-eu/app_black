// @vitest-environment jsdom
/**
 * MQTT and Loxone UDP are two entries in the settings menu, each with its own
 * form, save and restart badge — not two tabs behind one "Messaging
 * Protocols" entry that had to save and restore both at once.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import en from '@/locales/en/common.json';
import pl from '@/locales/pl/common.json';
import { ALL_SECTIONS } from '../constants/sectionDefinitions';
import MqttSectionForm from '../MqttSectionForm';
import LoxUdpSectionForm from '../LoxUdpSectionForm';

vi.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../MqttForm', () => ({
  default: () => <div>broker form</div>,
}));

afterEach(cleanup);

describe('settings menu', () => {
  it('lists MQTT and Loxone UDP as separate connection entries that need a restart', () => {
    for (const name of ['mqtt', 'lox_udp']) {
      const section = ALL_SECTIONS.find((s) => s.name === name);
      expect(section, name).toMatchObject({ group: 'connections', badge: 'restart' });
    }
  });

  it('names them for what they are, in both languages', () => {
    for (const locale of [en, pl]) {
      expect(locale.sections.mqtt).toBe('MQTT');
      expect(locale.sections.lox_udp).toBe('Loxone (UDP)');
      expect(locale.sections.descriptions.lox_udp).toBeTruthy();
    }
  });
});

describe('MqttSectionForm', () => {
  it('shows the broker form only, without a Loxone switch', () => {
    render(<MqttSectionForm data={{}} onChange={() => {}} />);

    expect(screen.getByText('broker form')).toBeTruthy();
    expect(screen.queryByText('messaging.enable_lox')).toBeNull();
  });

  it('switching it off keeps the rest of the section', async () => {
    const onChange = vi.fn();
    render(<MqttSectionForm data={{ host: 'localhost' }} onChange={onChange} />);

    await userEvent.click(screen.getByRole('checkbox'));

    expect(onChange).toHaveBeenCalledWith({ host: 'localhost', enabled: false });
  });
});

describe('LoxUdpSectionForm', () => {
  it('is off by default, and valid when off', () => {
    render(<LoxUdpSectionForm data={{}} onChange={() => {}} />);

    expect(screen.getByText('messaging.lox_disabled_info')).toBeTruthy();
    expect(screen.queryByText('messaging.enable_mqtt')).toBeNull();
  });

  it('switching it on enables the section, switching it off makes it valid', async () => {
    const onChange = vi.fn();
    const onValidationChange = vi.fn();
    const { rerender } = render(
      <LoxUdpSectionForm data={{}} onChange={onChange} onValidationChange={onValidationChange} />,
    );

    await userEvent.click(screen.getByRole('checkbox'));
    expect(onChange).toHaveBeenLastCalledWith({ enabled: true });

    rerender(
      <LoxUdpSectionForm
        data={{ enabled: true, host: '' }}
        onChange={onChange}
        onValidationChange={onValidationChange}
      />,
    );
    await userEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(onChange).toHaveBeenLastCalledWith({ enabled: false, host: '' });
    expect(onValidationChange).toHaveBeenLastCalledWith(true);
  });
});
