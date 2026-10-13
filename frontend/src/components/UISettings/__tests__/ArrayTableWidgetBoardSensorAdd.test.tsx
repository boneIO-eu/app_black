// @vitest-environment jsdom
/**
 * The board sensor form shows LM75 at 0x48 for an item with no type, and the
 * save sorts items into lm75/ina219/... by _type, dropping one without it. A
 * new board sensor therefore starts typed, as the form shows it.
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
vi.mock('../components/TableRenderer', () => ({ default: () => null }));
vi.mock('../components/EditItemDialog', () => ({
  default: (props: { open: boolean; editingItem: ConfigRecord; onSave: (e?: { formData?: ConfigRecord }) => void }) =>
    props.open ? (
      <button type="button" onClick={() => props.onSave({ formData: props.editingItem })}>save item</button>
    ) : null,
}));

const { default: ArrayTableWidget } = await import('../ArrayTableWidget');

describe('ArrayTableWidget board sensor add', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('saves a new board sensor untouched as an LM75 at 0x48', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<ArrayTableWidget value={[]} onChange={onChange} schema={{}} sectionType="board_sensors" />);
    await user.click(screen.getByText('settings.add_new'));
    await user.click(screen.getByText('save item'));
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ _type: 'lm75', address: 0x48 })]);
  });
});
