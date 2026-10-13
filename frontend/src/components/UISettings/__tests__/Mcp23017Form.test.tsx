// @vitest-environment jsdom
/**
 * The 48x4 has a third expander, mcp_middle. A change in the form must come
 * back with every expander and every field, or saving drops the 16 outputs
 * the form does not know by name.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

vi.mock('@/hooks/useTranslation', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@/api/axios', () => ({ default: { get: vi.fn().mockResolvedValue({ data: {} }) } }));

const { default: Mcp23017Form } = await import('../Mcp23017Form');

const MCP_48X4 = [
  { id: 'mcp_left', address: 35, inverted: true, init_sleep: '10ms' },
  { id: 'mcp_middle', address: 36, inverted: true },
  { id: 'mcp_right', address: 37, inverted: true },
];

describe('Mcp23017Form', () => {
  afterEach(cleanup);

  it('shows a card for every configured expander', () => {
    render(<Mcp23017Form data={MCP_48X4} onChange={() => {}} />);
    expect(screen.getByText('mcp_middle')).toBeTruthy();
    expect(screen.getAllByRole('combobox')).toHaveLength(3);
  });

  it('keeps every expander and field when one address changes', () => {
    const onChange = vi.fn();
    render(<Mcp23017Form data={MCP_48X4} onChange={onChange} />);
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: '0x26' } });
    expect(onChange).toHaveBeenCalledWith([
      { id: 'mcp_left', address: '0x23', inverted: true, init_sleep: '10ms' },
      { id: 'mcp_middle', address: '0x26', inverted: true },
      { id: 'mcp_right', address: '0x25', inverted: true },
    ]);
  });

  it('starts an empty section from the left/right pair', () => {
    render(<Mcp23017Form data={[]} onChange={() => {}} />);
    expect(screen.getByText('mcp_left')).toBeTruthy();
    expect(screen.getByText('mcp_right')).toBeTruthy();
  });
});
