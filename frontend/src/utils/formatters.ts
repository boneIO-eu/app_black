export const formatTimestamp = (timestamp?: number | null) => {
  if (!timestamp) return '—'; 
  try {
    if (timestamp === 0) return 'No updates yet';
    const date = new Date(timestamp * 1000); // Convert Unix timestamp to milliseconds
    return date.toLocaleTimeString();
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return 'Invalid timestamp';
  }
};

/**
 * Format a timeperiod value to a human-readable string.
 *
 * Accepts:
 *  - string with unit ("30s", "5min") — returned as-is
 *  - number — treated as milliseconds
 *  - TimePeriod object from backend ({seconds, minutes, hours, ...})
 */
export const formatTimeperiod = (
  value: number | string | { milliseconds?: number; seconds?: number; minutes?: number; hours?: number; _total_in_seconds?: number } | null | undefined,
): string => {
  if (value === null || value === undefined) return '';

  // If string with unit, return as-is
  if (typeof value === 'string') {
    if (/^\d+(\.\d+)?\s*(ms|s|sec|min|h|hours?)$/i.test(value)) {
      return value;
    }
    return value;
  }

  let ms: number;

  // If number, treat as milliseconds
  if (typeof value === 'number') {
    ms = value;
  }
  // If TimePeriod object from backend
  else if (typeof value === 'object') {
    if (value.hours !== undefined && value.hours > 0) {
      return `${value.hours}h`;
    }
    if (value.minutes !== undefined && value.minutes > 0) {
      return `${value.minutes}min`;
    }
    if (value.seconds !== undefined && value.seconds > 0) {
      return `${value.seconds}s`;
    }
    if (value.milliseconds !== undefined && value.milliseconds > 0) {
      return `${value.milliseconds}ms`;
    }
    // Fallback: use _total_in_seconds
    if (value._total_in_seconds !== undefined) {
      ms = value._total_in_seconds * 1000;
    } else {
      return '0ms';
    }
  } else {
    return '0ms';
  }

  // Format milliseconds to best unit
  if (ms >= 60000) {
    const minutes = ms / 60000;
    return minutes % 1 === 0 ? `${minutes}min` : `${ms}ms`;
  } else if (ms >= 1000) {
    const seconds = ms / 1000;
    return seconds % 1 === 0 ? `${seconds}s` : `${ms}ms`;
  }
  return `${ms}ms`;
};
