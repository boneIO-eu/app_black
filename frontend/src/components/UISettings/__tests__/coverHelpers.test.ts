/**
 * Tests for coverHelpers — isValidTimePeriod, timePeriodToMs,
 * validateCoverData, and buildCoverPayload.
 *
 * These tests verify that the cover form produces data the backend
 * can correctly process, specifically:
 * - Time period strings have correct format (e.g. "30s", not raw numbers)
 * - Venetian-specific fields are validated when platform = venetian
 * - Payload cleanup removes irrelevant fields
 */
import { describe, it, expect } from 'vitest';
import {
  isValidTimePeriod,
  timePeriodToMs,
  validateCoverData,
  buildCoverPayload,
} from '../helpers/coverHelpers';
import type { CoverFormData } from '../helpers/coverHelpers';

// ---------------------------------------------------------------------------
// isValidTimePeriod
// ---------------------------------------------------------------------------

describe('isValidTimePeriod', () => {
  it.each([
    '30s',
    '1000ms',
    '2min',
    '1h',
    '5sec',
    '2.5s',
    '500ms',
    '1hours',
  ])('accepts valid format: "%s"', (val) => {
    expect(isValidTimePeriod(val)).toBe(true);
  });

  it.each([
    '',
    '30',       // no unit
    'abc',      // no number
    '30xyz',    // unknown unit
    'ms30',     // wrong order
  ])('rejects invalid format: "%s"', (val) => {
    expect(isValidTimePeriod(val)).toBe(false);
  });

  it('rejects null and undefined', () => {
    expect(isValidTimePeriod(null)).toBe(false);
    expect(isValidTimePeriod(undefined)).toBe(false);
  });

  it('handles whitespace-padded strings', () => {
    expect(isValidTimePeriod('  30s  ')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// timePeriodToMs
// ---------------------------------------------------------------------------

describe('timePeriodToMs', () => {
  it('converts seconds', () => {
    expect(timePeriodToMs('30s')).toBe(30_000);
  });

  it('converts milliseconds', () => {
    expect(timePeriodToMs('1500ms')).toBe(1500);
  });

  it('converts minutes', () => {
    expect(timePeriodToMs('2min')).toBe(120_000);
  });

  it('converts hours', () => {
    expect(timePeriodToMs('1h')).toBe(3_600_000);
  });

  it('converts "sec" alias', () => {
    expect(timePeriodToMs('10sec')).toBe(10_000);
  });

  it('handles fractional values', () => {
    expect(timePeriodToMs('2.5s')).toBe(2500);
  });

  it('returns NaN for invalid format', () => {
    expect(timePeriodToMs('abc')).toBeNaN();
  });

  it('returns NaN for unitless number', () => {
    expect(timePeriodToMs('30')).toBeNaN();
  });
});

// ---------------------------------------------------------------------------
// validateCoverData
// ---------------------------------------------------------------------------

describe('validateCoverData', () => {
  const validTimeBased: CoverFormData = {
    id: 'cover_01_02',
    platform: 'time_based',
    open_relay: 'out_01',
    close_relay: 'out_02',
    open_time: '30s',
    close_time: '30s',
  };

  const validVenetian: CoverFormData = {
    id: 'cover_venetian_01',
    platform: 'venetian',
    open_relay: 'out_01',
    close_relay: 'out_02',
    open_time: '30s',
    close_time: '30s',
    tilt_duration: '5s',
  };

  it('returns no errors for valid time_based cover', () => {
    expect(validateCoverData(validTimeBased)).toEqual([]);
  });

  it('returns no errors for valid venetian cover', () => {
    expect(validateCoverData(validVenetian)).toEqual([]);
  });

  // --- Required fields ---

  it('requires open_relay', () => {
    const data = { ...validTimeBased, open_relay: '' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'open_relay')).toBe(true);
  });

  it('requires close_relay', () => {
    const data = { ...validTimeBased, close_relay: undefined };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'close_relay')).toBe(true);
  });

  it('requires open_time', () => {
    const data = { ...validTimeBased, open_time: '' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'open_time')).toBe(true);
  });

  it('requires close_time', () => {
    const data = { ...validTimeBased, close_time: undefined };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'close_time')).toBe(true);
  });

  // --- Same relay ---

  it('rejects same relay for open and close', () => {
    const data = { ...validTimeBased, open_relay: 'out_01', close_relay: 'out_01' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'close_relay' && e.messageKey === 'covers.same_relay_error')).toBe(true);
  });

  // --- Time format validation ---

  it('rejects open_time without unit', () => {
    const data = { ...validTimeBased, open_time: '30' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'open_time' && e.messageKey === 'covers.invalid_time_format')).toBe(true);
  });

  it('rejects close_time without unit', () => {
    const data = { ...validTimeBased, close_time: '30' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'close_time' && e.messageKey === 'covers.invalid_time_format')).toBe(true);
  });

  // --- Minimum duration ---

  it('rejects open_time below 1000ms', () => {
    const data = { ...validTimeBased, open_time: '500ms' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'open_time' && e.messageKey === 'covers.time_too_short')).toBe(true);
  });

  it('rejects close_time below 1000ms', () => {
    const data = { ...validTimeBased, close_time: '100ms' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'close_time' && e.messageKey === 'covers.time_too_short')).toBe(true);
  });

  it('accepts open_time of exactly 1s', () => {
    const data = { ...validTimeBased, open_time: '1s' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'open_time')).toBe(false);
  });

  // --- Venetian-specific ---

  it('requires tilt_duration for venetian', () => {
    const data = { ...validVenetian, tilt_duration: undefined };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'tilt_duration' && e.messageKey === 'covers.tilt_duration_required')).toBe(true);
  });

  it('rejects invalid tilt_duration format', () => {
    const data = { ...validVenetian, tilt_duration: '5' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'tilt_duration' && e.messageKey === 'covers.invalid_time_format')).toBe(true);
  });

  it('rejects tilt_duration below 10ms', () => {
    const data = { ...validVenetian, tilt_duration: '5ms' };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'tilt_duration' && e.messageKey === 'covers.tilt_too_short')).toBe(true);
  });

  it('does not require tilt_duration for time_based', () => {
    const data = { ...validTimeBased, tilt_duration: undefined };
    const errors = validateCoverData(data);
    expect(errors.some((e) => e.field === 'tilt_duration')).toBe(false);
  });

  // --- Multiple errors at once ---

  it('returns multiple errors for empty data', () => {
    const data: CoverFormData = {};
    const errors = validateCoverData(data);
    expect(errors.length).toBeGreaterThanOrEqual(4); // open_relay, close_relay, open_time, close_time
  });

  // --- Edge cases: various time formats the form might produce ---

  it.each([
    { input: '30s', expected: 30_000 },
    { input: '1000ms', expected: 1000 },
    { input: '2min', expected: 120_000 },
    { input: '1h', expected: 3_600_000 },
  ])('accepts time format "$input" (=$expected ms)', ({ input }) => {
    const data = { ...validTimeBased, open_time: input };
    const openTimeErrors = validateCoverData(data).filter((e) => e.field === 'open_time');
    expect(openTimeErrors).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// buildCoverPayload
// ---------------------------------------------------------------------------

describe('buildCoverPayload', () => {
  it('preserves all fields for venetian', () => {
    const data: CoverFormData = {
      id: 'cover_v1',
      platform: 'venetian',
      open_relay: 'out_01',
      close_relay: 'out_02',
      open_time: '30s',
      close_time: '30s',
      tilt_duration: '5s',
      tilt_restore_after_close: true,
    };
    const result = buildCoverPayload(data);
    expect(result.tilt_duration).toBe('5s');
    expect(result.tilt_restore_after_close).toBe(true);
  });

  it('removes tilt fields for time_based', () => {
    const data: CoverFormData = {
      id: 'cover_tb1',
      platform: 'time_based',
      open_relay: 'out_01',
      close_relay: 'out_02',
      open_time: '30s',
      close_time: '30s',
      tilt_duration: '5s',          // leftover from previous venetian config
      tilt_restore_after_close: true,
    };
    const result = buildCoverPayload(data);
    expect(result.tilt_duration).toBeUndefined();
    expect(result.tilt_restore_after_close).toBeUndefined();
  });

  it('sets default booleans', () => {
    const data: CoverFormData = {
      platform: 'time_based',
      open_relay: 'out_01',
      close_relay: 'out_02',
      open_time: '30s',
      close_time: '30s',
    };
    const result = buildCoverPayload(data);
    expect(result.restore_state).toBe(false);
    expect(result.show_in_ha).toBe(true);
  });

  it('does not override explicitly set booleans', () => {
    const data: CoverFormData = {
      platform: 'time_based',
      open_relay: 'out_01',
      close_relay: 'out_02',
      open_time: '30s',
      close_time: '30s',
      restore_state: true,
      show_in_ha: false,
    };
    const result = buildCoverPayload(data);
    expect(result.restore_state).toBe(true);
    expect(result.show_in_ha).toBe(false);
  });

  it('preserves time strings exactly as-is', () => {
    const data: CoverFormData = {
      platform: 'venetian',
      open_relay: 'out_01',
      close_relay: 'out_02',
      open_time: '25s',
      close_time: '35s',
      tilt_duration: '3s',
    };
    const result = buildCoverPayload(data);
    // These strings go directly to the backend which now handles
    // string → TimePeriod conversion via ensure_time_period()
    expect(result.open_time).toBe('25s');
    expect(result.close_time).toBe('35s');
    expect(result.tilt_duration).toBe('3s');
  });

  it('does not mutate original data', () => {
    const data: CoverFormData = {
      platform: 'time_based',
      open_relay: 'out_01',
      close_relay: 'out_02',
      open_time: '30s',
      close_time: '30s',
      tilt_duration: '5s',
    };
    const original = { ...data };
    buildCoverPayload(data);
    expect(data).toEqual(original);
  });

  // --- Simulated form submission scenarios ---

  it('simulates: new venetian cover creation', () => {
    const formData: CoverFormData = {
      id: 'cover_out_05_out_06',
      name: 'Salon Blinds',
      area: 'salon',
      platform: 'venetian',
      open_relay: 'out_05',
      close_relay: 'out_06',
      open_time: '30s',
      close_time: '30s',
      tilt_duration: '5s',
      tilt_restore_after_close: false,
      device_class: 'blind',
    };

    // Validate
    const errors = validateCoverData(formData);
    expect(errors).toEqual([]);

    // Build payload
    const payload = buildCoverPayload(formData);
    expect(payload.tilt_duration).toBe('5s');
    expect(payload.open_time).toBe('30s');
    expect(typeof payload.open_time).toBe('string');
    expect(typeof payload.tilt_duration).toBe('string');
  });

  it('simulates: platform change venetian → time_based', () => {
    // User had venetian, changed to time_based
    const formData: CoverFormData = {
      id: 'cover_out_05_out_06',
      platform: 'time_based', // changed from venetian
      open_relay: 'out_05',
      close_relay: 'out_06',
      open_time: '30s',
      close_time: '30s',
      tilt_duration: '5s',           // stale from previous venetian config
      tilt_restore_after_close: true, // stale
    };

    const payload = buildCoverPayload(formData);
    // tilt fields should be removed
    expect(payload.tilt_duration).toBeUndefined();
    expect(payload.tilt_restore_after_close).toBeUndefined();
    // rest should be preserved
    expect(payload.open_time).toBe('30s');
    expect(payload.close_time).toBe('30s');
  });

  it('simulates: time change on existing cover', () => {
    // User changes open_time from 30s to 25s via the form
    const formData: CoverFormData = {
      id: 'cover_out_05_out_06',
      platform: 'venetian',
      open_relay: 'out_05',
      close_relay: 'out_06',
      open_time: '25s',   // changed
      close_time: '30s',
      tilt_duration: '5s',
    };

    const errors = validateCoverData(formData);
    expect(errors).toEqual([]);

    const payload = buildCoverPayload(formData);
    // Backend will receive "25s" as string and ensure_time_period()
    // will convert it to TimePeriod(seconds=25)
    expect(payload.open_time).toBe('25s');
    expect(typeof payload.open_time).toBe('string');
  });
});
