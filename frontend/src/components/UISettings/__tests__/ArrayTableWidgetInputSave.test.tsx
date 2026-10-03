// @vitest-environment jsdom
/**
 * Saving an input in its dialog commits the section: the user used to have to
 * press Save a second time on the section bar before the device saw anything.
 * The dialog stays open, and cannot be closed, until that save lands, so the
 * next edit cannot start on a list the finishing save is about to replace.
 */
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
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
    <button type="button" onClick={() => onEdit(0)}>edit first</button>
  ),
}));

vi.mock('../components/EditItemDialog', () => ({
  default: (props: {
    open: boolean;
    isSaving?: boolean;
    editingItem: ConfigRecord | null;
    onSave: (e?: { formData?: ConfigRecord }) => void;
    onOpenChange: (open: boolean) => void;
  }) =>
    props.open ? (
      <div>
        <span>{props.isSaving ? 'saving' : 'idle'}</span>
        <button type="button" onClick={() => props.onSave({ formData: { ...props.editingItem, name: 'Hall' } })}>
          save item
        </button>
        <button type="button" onClick={() => props.onOpenChange(false)}>close dialog</button>
      </div>
    ) : null,
}));

const { default: ArrayTableWidget } = await import('../ArrayTableWidget');

const ITEMS: ConfigRecord[] = [{ name: 'IN_01', boneio_input: 'in_01', boneio_output: 'out_01', _type: 'event' }];

function Host({ sectionType, onSaveSection }: {
  sectionType: 'local_inputs' | 'output';
  onSaveSection: (section: string, data?: unknown[]) => Promise<void>;
}) {
  const [value, setValue] = useState<ConfigRecord[]>(ITEMS);
  return (
    <ArrayTableWidget
      value={value}
      onChange={setValue}
      schema={{}}
      sectionType={sectionType}
      onSaveSection={onSaveSection}
    />
  );
}

describe('ArrayTableWidget input save', () => {
  afterEach(cleanup);

  it('commits the section from the dialog and holds the dialog until it lands', async () => {
    let finish: () => void = () => {};
    const onSaveSection = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    const user = userEvent.setup();
    render(<Host sectionType="local_inputs" onSaveSection={onSaveSection} />);

    await user.click(screen.getByText('edit first'));
    await user.click(screen.getByText('save item'));

    expect(onSaveSection).toHaveBeenCalledTimes(1);
    expect(onSaveSection).toHaveBeenCalledWith('local_inputs', [{ ...ITEMS[0], name: 'Hall' }]);
    expect(screen.getByText('saving')).toBeTruthy();

    await user.click(screen.getByText('close dialog'));
    await user.click(screen.getByText('save item'));
    expect(screen.getByText('saving')).toBeTruthy();
    expect(onSaveSection).toHaveBeenCalledTimes(1);

    finish();
    await waitFor(() => expect(screen.queryByText('save item')).toBeNull());
  });

  it('leaves other sections to the section bar', async () => {
    const onSaveSection = vi.fn(() => Promise.resolve());
    const user = userEvent.setup();
    render(<Host sectionType="output" onSaveSection={onSaveSection} />);

    await user.click(screen.getByText('edit first'));
    await user.click(screen.getByText('save item'));

    expect(onSaveSection).not.toHaveBeenCalled();
    expect(screen.queryByText('save item')).toBeNull();
  });
});
