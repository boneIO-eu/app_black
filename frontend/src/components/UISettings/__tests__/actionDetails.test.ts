/**
 * Tests for ActionDetails helper — hasActions function.
 */
import { describe, it, expect } from 'vitest';
import { hasActions } from '../components/ActionDetails';

describe('hasActions', () => {
  it('returns false for empty actions', () => {
    expect(hasActions({})).toBe(false);
    expect(hasActions({ actions: {} })).toBe(false);
    expect(hasActions({ actions: { single: [], double: [], pressed: [] } })).toBe(false);
  });

  it('detects event actions (single, double, long)', () => {
    expect(hasActions({ actions: { single: [{ action: 'output' }] } })).toBe(true);
    expect(hasActions({ actions: { double: [{ action: 'output' }] } })).toBe(true);
    expect(hasActions({ actions: { long: [{ action: 'cover' }] } })).toBe(true);
    expect(hasActions({ actions: { triple: [{ action: 'output' }] } })).toBe(true);
  });

  it('detects binary_sensor actions (pressed, released)', () => {
    expect(hasActions({ actions: { pressed: [{ action: 'output' }] } })).toBe(true);
    expect(hasActions({ actions: { released: [{ action: 'output' }] } })).toBe(true);
  });

  it('detects sequence actions', () => {
    expect(hasActions({
      actions: { double_then_long: [{ action: 'output' }] },
    })).toBe(true);
  });

  it('returns false when actions is not an object', () => {
    expect(hasActions({ actions: null })).toBe(false);
    expect(hasActions({ actions: 'string' })).toBe(false);
  });
});
