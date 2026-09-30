// @vitest-environment jsdom
/**
 * The debounce field under a binary sensor: 1–1000 ms, and it has to let the
 * user clear it to type a new value instead of snapping back to the default.
 */
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BounceTimeInput, { BOUNCE_TIME_MAX_MS, BOUNCE_TIME_MIN_MS } from '../widgets/BounceTimeInput';

afterEach(cleanup);

/**
 * Tap the field and type, the way a person does: focus selects the whole
 * content one frame later, so typing starts after that frame and replaces it.
 */
async function typeInto(el: HTMLElement, text: string) {
  await userEvent.click(el);
  await new Promise((resolve) => requestAnimationFrame(resolve));
  await userEvent.keyboard(text);
}

/** Holds bounce_time the way BinarySensorForm's data does. */
function Form({ initial, onChange }: { initial?: unknown; onChange?: (ms: number) => void }) {
  const [bounce, setBounce] = useState<unknown>(initial);
  return (
    <>
      <label htmlFor="bounce">bounce</label>
      <BounceTimeInput
        id="bounce"
        value={bounce}
        defaultMs={120}
        onChange={(ms) => {
          setBounce(ms);
          onChange?.(ms);
        }}
      />
      <button type="button">elsewhere</button>
    </>
  );
}

const field = () => screen.getByLabelText('bounce') as HTMLInputElement;

describe('BounceTimeInput', () => {
  it('shows the default when nothing is stored', () => {
    render(<Form />);
    expect(field().value).toBe('120');
  });

  it('reads a stored value with a unit', () => {
    render(<Form initial="50ms" />);
    expect(field().value).toBe('50');
  });

  it('can be cleared and retyped without jumping back to the default', async () => {
    const onChange = vi.fn();
    render(<Form onChange={onChange} />);
    await userEvent.clear(field());
    expect(field().value).toBe('');
    expect(onChange).not.toHaveBeenCalled();

    await typeInto(field(), '80');
    expect(field().value).toBe('80');
    expect(onChange).toHaveBeenLastCalledWith(80);
  });

  it('shows the stored value again when left empty', async () => {
    const onChange = vi.fn();
    render(<Form initial={60} onChange={onChange} />);
    await userEvent.clear(field());
    await userEvent.tab();
    expect(field().value).toBe('60');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('caps the value at the maximum while typing', async () => {
    const onChange = vi.fn();
    render(<Form onChange={onChange} />);
    await userEvent.clear(field());
    await typeInto(field(), '5000');
    expect(field().value).toBe(String(BOUNCE_TIME_MAX_MS));
    expect(onChange).toHaveBeenLastCalledWith(BOUNCE_TIME_MAX_MS);
  });

  it('raises zero to the minimum when the field loses focus', async () => {
    const onChange = vi.fn();
    render(<Form onChange={onChange} />);
    await userEvent.clear(field());
    await typeInto(field(), '0');
    await userEvent.tab();
    expect(field().value).toBe(String(BOUNCE_TIME_MIN_MS));
    expect(onChange).toHaveBeenLastCalledWith(BOUNCE_TIME_MIN_MS);
  });
});
