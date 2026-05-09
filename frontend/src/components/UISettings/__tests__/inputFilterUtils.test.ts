/**
 * Tests for input pin filtering utilities.
 *
 * These tests guard against the case-sensitivity bug where binary_sensor
 * pins stored as lowercase ('in_48') were not cross-matched against
 * event pins stored as uppercase ('IN_48'), allowing duplicate pin usage.
 */
import { describe, it, expect } from 'vitest';
import {
  collectUsedInputs,
  getInputAvailability,
  buildInputOptions,
} from '../helpers/inputFilterUtils';

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

/** Schema-like enum: all possible pins (uppercase, like the JSON schema). */
const ALL_PINS = ['IN_01', 'IN_02', 'IN_03', 'IN_04', 'IN_05'];

// ---------------------------------------------------------------------------
// collectUsedInputs
// ---------------------------------------------------------------------------
describe('collectUsedInputs', () => {
  it('returns empty array for empty input', () => {
    expect(collectUsedInputs([])).toEqual([]);
  });

  it('collects pins and normalizes to uppercase', () => {
    const entities = [
      { boneio_input: 'in_01' },
      { boneio_input: 'IN_02' },
    ];
    expect(collectUsedInputs(entities)).toEqual(['IN_01', 'IN_02']);
  });

  it('skips entities without boneio_input', () => {
    const entities = [
      { boneio_input: 'IN_01' },
      { boneio_input: undefined },
      {},
    ];
    expect(collectUsedInputs(entities)).toEqual(['IN_01']);
  });

  it('excludes entity at editingIndex', () => {
    const entities = [
      { boneio_input: 'IN_01' },
      { boneio_input: 'IN_02' },
      { boneio_input: 'IN_03' },
    ];
    expect(collectUsedInputs(entities, 1)).toEqual(['IN_01', 'IN_03']);
  });

  it('does not exclude anything when editingIndex is null', () => {
    const entities = [
      { boneio_input: 'IN_01' },
      { boneio_input: 'IN_02' },
    ];
    expect(collectUsedInputs(entities, null)).toEqual(['IN_01', 'IN_02']);
  });
});

// ---------------------------------------------------------------------------
// getInputAvailability
// ---------------------------------------------------------------------------
describe('getInputAvailability', () => {
  it('returns all pins available when nothing is used', () => {
    const { usedInputs, availableInputs } = getInputAvailability(
      ALL_PINS, [], [], null, 'binary_sensor',
    );
    expect(usedInputs).toEqual([]);
    expect(availableInputs).toEqual(ALL_PINS);
  });

  it('filters BS pins when editing event (cross-section blocking)', () => {
    const binarySensors = [{ boneio_input: 'IN_01' }];
    const events: any[] = [];

    const { usedInputs, availableInputs } = getInputAvailability(
      ALL_PINS, binarySensors, events, null, 'event',
    );

    expect(usedInputs).toContain('IN_01');
    expect(availableInputs).not.toContain('IN_01');
    expect(availableInputs).toContain('IN_02');
  });

  it('filters event pins when editing BS (cross-section blocking)', () => {
    const binarySensors: any[] = [];
    const events = [{ boneio_input: 'IN_03' }];

    const { usedInputs, availableInputs } = getInputAvailability(
      ALL_PINS, binarySensors, events, null, 'binary_sensor',
    );

    expect(usedInputs).toContain('IN_03');
    expect(availableInputs).not.toContain('IN_03');
  });

  // ======== THE REGRESSION TEST for the original bug ========
  it('blocks lowercase BS pin when editing event (case-insensitive)', () => {
    // Binary sensor stores pin as lowercase (from YAML)
    const binarySensors = [{ boneio_input: 'in_04' }];
    const events: any[] = [];

    const { usedInputs, availableInputs } = getInputAvailability(
      ALL_PINS, binarySensors, events, null, 'event',
    );

    // 'in_04' (lowercase) should still block 'IN_04' (uppercase schema pin)
    expect(usedInputs).toContain('IN_04');
    expect(availableInputs).not.toContain('IN_04');
  });

  it('blocks uppercase event pin when editing BS with lowercase data', () => {
    // Event stores pin uppercase, BS data lowercase
    const binarySensors = [{ boneio_input: 'in_01' }];
    const events = [{ boneio_input: 'IN_02' }];

    const { usedInputs, availableInputs } = getInputAvailability(
      ALL_PINS, binarySensors, events, null, 'binary_sensor',
    );

    expect(usedInputs).toContain('IN_01');
    expect(usedInputs).toContain('IN_02');
    expect(availableInputs).toEqual(['IN_03', 'IN_04', 'IN_05']);
  });

  it('excludes editingIndex only from own section', () => {
    // Editing binary_sensor at index 0 — its pin should NOT be in usedInputs
    const binarySensors = [
      { boneio_input: 'IN_01' },
      { boneio_input: 'IN_02' },
    ];
    const events = [{ boneio_input: 'IN_03' }];

    const { usedInputs, availableInputs } = getInputAvailability(
      ALL_PINS, binarySensors, events, 0, 'binary_sensor',
    );

    // IN_01 is the one being edited, should be available
    expect(usedInputs).not.toContain('IN_01');
    expect(availableInputs).toContain('IN_01');
    // IN_02 (other BS) and IN_03 (event) should still be blocked
    expect(usedInputs).toContain('IN_02');
    expect(usedInputs).toContain('IN_03');
    expect(availableInputs).not.toContain('IN_02');
    expect(availableInputs).not.toContain('IN_03');
  });

  it('excludes editingIndex from event section, not BS', () => {
    const binarySensors = [{ boneio_input: 'IN_01' }];
    const events = [
      { boneio_input: 'IN_02' },
      { boneio_input: 'IN_03' },
    ];

    const { usedInputs, availableInputs } = getInputAvailability(
      ALL_PINS, binarySensors, events, 0, 'event',
    );

    // IN_02 (event index 0, being edited) should be available
    expect(availableInputs).toContain('IN_02');
    // IN_01 (BS) and IN_03 (other event) should be blocked
    expect(availableInputs).not.toContain('IN_01');
    expect(availableInputs).not.toContain('IN_03');
  });

  it('handles mixed case across both sections', () => {
    // Real-world scenario: BS lowercase, events uppercase
    const binarySensors = [
      { boneio_input: 'in_01' },
      { boneio_input: 'in_02' },
    ];
    const events = [
      { boneio_input: 'IN_03' },
      { boneio_input: 'IN_04' },
    ];

    const { availableInputs } = getInputAvailability(
      ALL_PINS, binarySensors, events, null, 'binary_sensor',
    );

    expect(availableInputs).toEqual(['IN_05']);
  });

  it('deduplicates when same pin appears in both sections (mixed case)', () => {
    // Edge case: same pin appears in both (shouldn't happen, but be safe)
    const binarySensors = [{ boneio_input: 'in_01' }];
    const events = [{ boneio_input: 'IN_01' }];

    const { usedInputs } = getInputAvailability(
      ALL_PINS, binarySensors, events, null, 'binary_sensor',
    );

    // Should be deduplicated, both map to 'IN_01'
    expect(usedInputs).toEqual(['IN_01']);
  });
});

// ---------------------------------------------------------------------------
// buildInputOptions
// ---------------------------------------------------------------------------
describe('buildInputOptions', () => {
  it('returns available inputs when no current input', () => {
    expect(buildInputOptions(['IN_01', 'IN_02'], undefined)).toEqual([
      'IN_01', 'IN_02',
    ]);
  });

  it('returns available inputs when current is already available', () => {
    expect(buildInputOptions(['IN_01', 'IN_02'], 'IN_01')).toEqual([
      'IN_01', 'IN_02',
    ]);
  });

  it('adds current input to list when it is used elsewhere', () => {
    // Current pin is IN_03, which is NOT in available list
    const result = buildInputOptions(['IN_01', 'IN_02'], 'IN_03');
    expect(result).toContain('IN_03');
    expect(result).toContain('IN_01');
    expect(result).toContain('IN_02');
  });

  it('handles case mismatch between current and available', () => {
    // Current is lowercase, available has uppercase version
    const result = buildInputOptions(['IN_01', 'IN_02'], 'in_01');
    // 'in_01' matches 'IN_01' case-insensitively → already available
    expect(result).toEqual(['IN_01', 'IN_02']);
  });

  it('adds lowercase current pin when not matching any available pin', () => {
    const result = buildInputOptions(['IN_01', 'IN_02'], 'in_03');
    expect(result).toContain('in_03');
    // Should be sorted
    expect(result).toEqual(['IN_01', 'IN_02', 'in_03'].sort());
  });
});
