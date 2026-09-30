// @vitest-environment jsdom
/**
 * NumericInput is a text field with a numeric keyboard, so the filtering a
 * `type="number"` input would do is ours: these pin it down.
 */
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NumericInput, type NumericInputProps } from '../NumericInput';

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

/** A parent that holds the value, the way every form does. */
function Controlled(props: Partial<NumericInputProps> & { initial?: number | '' }) {
  const { initial = '', onChange, ...rest } = props;
  const [value, setValue] = useState<number | ''>(initial);
  return (
    <NumericInput
      aria-label="value"
      {...rest}
      value={value}
      onChange={(v) => {
        setValue(v);
        onChange?.(v);
      }}
    />
  );
}

const field = () => screen.getByLabelText('value') as HTMLInputElement;

describe('NumericInput', () => {
  it('asks the phone for a numeric keyboard, not type=number', () => {
    render(<Controlled />);
    expect(field().type).toBe('text');
    expect(field().inputMode).toBe('numeric');
  });

  it('asks for a decimal keyboard when decimals are allowed', () => {
    render(<Controlled decimal />);
    expect(field().inputMode).toBe('decimal');
  });

  it('ignores letters and other non-digits', async () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    await typeInto(field(), '1a2e3');
    expect(field().value).toBe('123');
    expect(onChange).toHaveBeenLastCalledWith(123);
  });

  it('reads a Polish decimal comma as a point', async () => {
    const onChange = vi.fn();
    render(<Controlled decimal onChange={onChange} />);
    await typeInto(field(), '2,5');
    expect(onChange).toHaveBeenLastCalledWith(2.5);
  });

  it('can be emptied', async () => {
    const onChange = vi.fn();
    render(<Controlled initial={42} onChange={onChange} />);
    await userEvent.clear(field());
    expect(field().value).toBe('');
    expect(onChange).toHaveBeenLastCalledWith('');
  });

  it('raises a value below the minimum when the field loses focus', async () => {
    render(<Controlled min={1} max={10} />);
    await typeInto(field(), '0');
    await userEvent.tab();
    expect(field().value).toBe('1');
  });
});

describe('NumericInput while typing', () => {
  it('keeps a decimal point typed before the fraction', async () => {
    const onChange = vi.fn();
    render(<Controlled decimal onChange={onChange} />);
    await typeInto(field(), '0.25');
    expect(field().value).toBe('0.25');
    expect(onChange).toHaveBeenLastCalledWith(0.25);
  });

  it('keeps a leading minus sign', async () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    await typeInto(field(), '-7');
    expect(field().value).toBe('-7');
    expect(onChange).toHaveBeenLastCalledWith(-7);
  });

  it('caps a positive number at the maximum as it is typed', async () => {
    const onChange = vi.fn();
    render(<Controlled max={100} onChange={onChange} />);
    await typeInto(field(), '250');
    expect(field().value).toBe('100');
    expect(onChange).toHaveBeenLastCalledWith(100);
  });

  it('does not cap a negative number mid-typing', async () => {
    const onChange = vi.fn();
    render(<Controlled min={-20} max={-5} onChange={onChange} />);
    await typeInto(field(), '-10');
    expect(field().value).toBe('-10');
    expect(onChange).toHaveBeenLastCalledWith(-10);
  });

  it('shows the parent value again after focus leaves', async () => {
    render(<Controlled decimal initial={3} />);
    await userEvent.clear(field());
    await typeInto(field(), '4,50');
    await userEvent.tab();
    expect(field().value).toBe('4.5');
  });
});
