/**
 * Cover form helpers — data validation and sanitization.
 *
 * Extracted from CoverForm.tsx for testability.
 */

/** Backend-compatible cover data shape. */
export interface CoverFormData {
  id?: string;
  name?: string;
  area?: string;
  platform?: 'time_based' | 'venetian';
  open_relay?: string;
  close_relay?: string;
  open_time?: string;
  close_time?: string;
  tilt_duration?: string;
  tilt_restore_after_close?: boolean;
  device_class?: string;
  restore_state?: boolean;
  show_in_ha?: boolean;
}

/** Time period format regex — number + unit (e.g. "30s", "1000ms"). */
const TIME_PERIOD_RE = /^\d+(?:\.\d+)?\s*(?:ms|s|sec|min|h|hours?)$/i;

/**
 * Validate that a time period string has the correct format.
 *
 * @param value - The string to validate.
 * @returns `true` if format is valid.
 */
export function isValidTimePeriod(value: string | undefined | null): boolean {
  if (!value) return false;
  return TIME_PERIOD_RE.test(value.trim());
}

/**
 * Parse a time period string to milliseconds.
 *
 * @param value - Time string like "30s", "1000ms", "2min".
 * @returns Milliseconds, or `NaN` if invalid.
 */
export function timePeriodToMs(value: string): number {
  const match = value.trim().match(/^(\d+(?:\.\d+)?)\s*(ms|s|sec|min|mins|h|hours?)$/i);
  if (!match) return NaN;
  const num = parseFloat(match[1]);
  const unit = match[2].toLowerCase();
  switch (unit) {
    case 'ms':
      return num;
    case 's':
    case 'sec':
      return num * 1000;
    case 'min':
    case 'mins':
      return num * 60_000;
    case 'h':
    case 'hour':
    case 'hours':
      return num * 3_600_000;
    default:
      return NaN;
  }
}

/** Validation error entry. */
export interface CoverValidationError {
  field: string;
  messageKey: string;
}

/**
 * Validate cover form data before submission.
 *
 * Checks all required fields, time period formats, minimum durations,
 * and platform-specific requirements.
 *
 * @param data - Cover form data to validate.
 * @returns Array of validation errors (empty = valid).
 */
export function validateCoverData(data: CoverFormData): CoverValidationError[] {
  const errors: CoverValidationError[] = [];

  // Required relay fields
  if (!data.open_relay) {
    errors.push({ field: 'open_relay', messageKey: 'covers.open_relay_required' });
  }
  if (!data.close_relay) {
    errors.push({ field: 'close_relay', messageKey: 'covers.close_relay_required' });
  }

  // Same relay check
  if (data.open_relay && data.close_relay && data.open_relay === data.close_relay) {
    errors.push({ field: 'close_relay', messageKey: 'covers.same_relay_error' });
  }

  // Open time
  if (!data.open_time) {
    errors.push({ field: 'open_time', messageKey: 'covers.open_time_required' });
  } else if (!isValidTimePeriod(data.open_time)) {
    errors.push({ field: 'open_time', messageKey: 'covers.invalid_time_format' });
  } else {
    const ms = timePeriodToMs(data.open_time);
    if (ms < 1000) {
      errors.push({ field: 'open_time', messageKey: 'covers.time_too_short' });
    }
  }

  // Close time
  if (!data.close_time) {
    errors.push({ field: 'close_time', messageKey: 'covers.close_time_required' });
  } else if (!isValidTimePeriod(data.close_time)) {
    errors.push({ field: 'close_time', messageKey: 'covers.invalid_time_format' });
  } else {
    const ms = timePeriodToMs(data.close_time);
    if (ms < 1000) {
      errors.push({ field: 'close_time', messageKey: 'covers.time_too_short' });
    }
  }

  // Venetian-specific
  if (data.platform === 'venetian') {
    if (!data.tilt_duration) {
      errors.push({ field: 'tilt_duration', messageKey: 'covers.tilt_duration_required' });
    } else if (!isValidTimePeriod(data.tilt_duration)) {
      errors.push({ field: 'tilt_duration', messageKey: 'covers.invalid_time_format' });
    } else {
      const ms = timePeriodToMs(data.tilt_duration);
      if (ms < 10) {
        errors.push({ field: 'tilt_duration', messageKey: 'covers.tilt_too_short' });
      }
    }
  }

  return errors;
}

/**
 * Build sanitized cover data for backend submission.
 *
 * Removes platform-specific fields that don't apply and ensures
 * all time values are string format (e.g. "30s").
 *
 * @param data - Raw form data.
 * @returns Cleaned data ready for API submission.
 */
export function buildCoverPayload(data: CoverFormData): CoverFormData {
  const result: CoverFormData = { ...data };

  // Remove venetian fields when not venetian
  if (result.platform !== 'venetian') {
    delete result.tilt_duration;
    delete result.tilt_restore_after_close;
  }

  // Ensure boolean defaults
  if (result.restore_state === undefined) {
    result.restore_state = false;
  }
  if (result.show_in_ha === undefined) {
    result.show_in_ha = true;
  }

  return result;
}
