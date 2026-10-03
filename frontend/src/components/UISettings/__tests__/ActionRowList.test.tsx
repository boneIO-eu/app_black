// @vitest-environment jsdom
/**
 * One choice in an action editor can be several onUpdate calls: picking a
 * cover's action sets action_cover and then the data that action reads. Each
 * has to land on the result of the one before it, or the cover action is lost
 * and the row falls back to TOGGLE whatever was picked.
 */
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ActionEntry } from '../helpers/actionSummary';

vi.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// The real editor is a Radix select per field; this one makes the two calls
// CoverAction makes for one pick.
vi.mock('../ActionFields', async (importOriginal) => {
  const original = await importOriginal<typeof import('../ActionFields')>();
  return {
    ...original,
    default: ({ onUpdate }: { onUpdate: (field: string, value: unknown) => void }) => (
      <button
        type="button"
        onClick={() => {
          onUpdate('action_cover', 'CLOSE');
          onUpdate('data', undefined);
        }}
      >
        pick close
      </button>
    ),
  };
});

const { default: ActionRowList } = await import('../ActionFields/ActionRowList');

/** Holds the list the way VirtualSwitchForm and ScheduleForm do. */
function Form({ onChange }: { onChange: (actions: ActionEntry[]) => void }) {
  const [actions, setActions] = useState<ActionEntry[]>([
    { action: 'cover', boneio_cover: 'living_room', action_cover: 'TOGGLE' },
  ]);
  return (
    <ActionRowList
      actions={actions}
      onChange={(next) => {
        setActions(next);
        onChange(next);
      }}
      newAction={() => ({ action: 'output' })}
      emptyText="none"
      entities={{ allOutputs: [], allOutputGroups: [], allCovers: [], allAreas: [] }}
      actionTypeOptions={['cover']}
      actionOutputOptions={[]}
      actionCoverOptions={['TOGGLE', 'CLOSE']}
    />
  );
}

afterEach(cleanup);

describe('ActionRowList', () => {
  it('keeps every field of one choice made in several calls', async () => {
    const onChange = vi.fn();
    const { container } = render(<Form onChange={onChange} />);
    // Open the row, then make the pick.
    await userEvent.click(container.querySelector('.cursor-pointer') as HTMLElement);
    await userEvent.click(screen.getByText('pick close'));

    const last = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0] as ActionEntry[];
    expect(last[0]).toMatchObject({ action: 'cover', boneio_cover: 'living_room', action_cover: 'CLOSE' });
  });
});
