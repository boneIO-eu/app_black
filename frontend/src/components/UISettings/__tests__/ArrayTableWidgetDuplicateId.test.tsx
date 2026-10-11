// @vitest-environment jsdom
/**
 * Two entities with one id share their MQTT topics and HA entity, so the
 * second silently replaces the first. A cover keeps the id generated from its
 * first relays; the dialog refuses a save that would collide.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ConfigRecord } from '@/types/jsonSchema';

vi.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('../../../hooks/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../components/TableRenderer', () => ({
  default: ({ onEdit }: { onEdit: (index: number) => void }) => (
    <button type="button" onClick={() => onEdit(1)}>edit second</button>
  ),
}));

let saved: ConfigRecord = {};
vi.mock('../components/EditItemDialog', () => ({
  default: (props: { open: boolean; onSave: (e?: { formData?: ConfigRecord }) => void }) =>
    props.open ? (
      <button type="button" onClick={() => props.onSave({ formData: saved })}>save item</button>
    ) : null,
}));

const { default: ArrayTableWidget } = await import('../ArrayTableWidget');

const TIMES = { open_time: '30s', close_time: '30s' };
const COVERS: ConfigRecord[] = [
  { id: 'cover_out_01_out_02', open_relay: 'out_01', close_relay: 'out_02', ...TIMES },
  { id: 'cover_out_03_out_04', open_relay: 'out_03', close_relay: 'out_04', ...TIMES },
];

async function save(item: ConfigRecord) {
  saved = item;
  const onChange = vi.fn();
  const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});
  const user = userEvent.setup();
  render(<ArrayTableWidget value={COVERS} onChange={onChange} schema={{}} sectionType="cover" />);
  await user.click(screen.getByText('edit second'));
  await user.click(screen.getByText('save item'));
  return { onChange, alert };
}

describe('ArrayTableWidget duplicate id', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('refuses a cover whose id another cover already has', async () => {
    const { onChange, alert } = await save({ ...COVERS[1], id: 'cover_out_01_out_02' });
    expect(alert).toHaveBeenCalledWith('array_table_widget.id_duplicate');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('refuses a cover without an id whose relays give a taken one', async () => {
    const { onChange, alert } = await save({ open_relay: 'out_01', close_relay: 'out_02', ...TIMES });
    expect(alert).toHaveBeenCalledWith('array_table_widget.id_duplicate');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('saves the cover under its own id', async () => {
    const { onChange, alert } = await save({ ...COVERS[1], name: 'Kitchen' });
    expect(alert).not.toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledWith([COVERS[0], { ...COVERS[1], name: 'Kitchen' }]);
  });
});
