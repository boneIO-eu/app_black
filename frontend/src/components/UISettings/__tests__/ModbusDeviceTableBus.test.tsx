// @vitest-environment jsdom
/**
 * The device table names each device's bus once there is more than one.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import ModbusDeviceTable from '../tables/ModbusDeviceTable';

vi.mock('../../../hooks/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

afterEach(cleanup);

const devices = [
  { id: 'licznik', address: 1, model: 'sdm630' },
  { id: 'pc', address: 1, model: 'sdm630', bus: 'pompa' },
];

function table(busIds: string[]) {
  return render(
    <ModbusDeviceTable
      items={devices}
      allAreas={[]}
      onEdit={() => {}}
      onDelete={() => {}}
      formatTimeperiod={String}
      busIds={busIds}
    />,
  );
}

describe('ModbusDeviceTable bus column', () => {
  it('shows each device on its bus, the first bus for one that names none', () => {
    table(['rs485', 'pompa']);
    const rows = screen.getAllByRole('row').slice(1).map((r) => r.textContent ?? '');
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toContain('modbus.bus');
    expect(rows[0]).toContain('rs485');
    expect(rows[1]).toContain('pompa');
  });

  it('has no bus column with a single bus', () => {
    table(['rs485']);
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).not.toContain('modbus.bus');
  });
});
