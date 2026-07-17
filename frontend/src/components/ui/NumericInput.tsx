import React, { useRef, useCallback } from 'react';
import { cn } from '@/lib/utils';

export interface NumericInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'onChange' | 'value' | 'inputMode'> {
  /** Current numeric value (number or empty string for blank input) */
  value: number | '';
  /** Called with parsed numeric value or '' when input is cleared */
  onChange: (value: number | '') => void;
  /** Allow decimal numbers (shows decimal keyboard on mobile) */
  decimal?: boolean;
  /** Minimum allowed value (validated on blur) */
  min?: number;
  /** Maximum allowed value (validated on blur) */
  max?: number;
  /** Step for increment/decrement (informational only) */
  step?: number;
}

/**
 * Numeric input that uses `type="text"` with `inputMode="numeric"` or `"decimal"`.
 *
 * Advantages over `<input type="number">`:
 * - No spinner arrows (cleaner look)
 * - No accidental scroll-wheel value changes
 * - No unexpected `e`/`E` scientific notation input
 * - Better mobile keyboard control per locale
 * - Handles Polish comma separator (`2,5` → `2.5`)
 * - Auto-selects content on focus for fast editing on mobile
 *
 * @example
 * // Integer input (address, port, etc.)
 * <NumericInput value={1} min={1} max={247} onChange={setAddress} />
 *
 * // Decimal input (calibration offset, timeout, etc.)
 * <NumericInput value={2.5} decimal min={-10} max={10} step={0.1} onChange={setOffset} />
 */
export function NumericInput({
  value,
  onChange,
  decimal = false,
  min,
  max,
  step,
  className,
  onBlur,
  ...props
}: NumericInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  /**
   * Format the display value — show empty string for blank,
   * otherwise show the number as-is.
   */
  const displayValue = value === '' ? '' : String(value);

  /**
   * Filter and parse input characters.
   * Allows: digits, one decimal separator (. or ,), leading minus sign.
   */
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const raw = e.target.value;

      // Allow empty input
      if (raw === '' || raw === '-') {
        onChange(raw === '-' ? ('' as const) : '');
        return;
      }

      // Normalize comma to dot for parsing
      const normalized = raw.replace(',', '.');

      // Validate allowed characters
      const pattern = decimal
        ? /^-?\d*\.?\d*$/
        : /^-?\d*$/;

      if (!pattern.test(normalized)) {
        return; // Reject invalid characters silently
      }

      // Parse the value
      const parsed = decimal
        ? parseFloat(normalized)
        : parseInt(normalized, 10);

      if (Number.isNaN(parsed)) {
        // Allow intermediate states like "1." or "-"
        return;
      }

      onChange(parsed);
    },
    [onChange, decimal]
  );

  /**
   * Clamp value to min/max on blur and handle intermediate states.
   */
  const handleBlur = useCallback(
    (e: React.FocusEvent<HTMLInputElement>) => {
      if (value !== '' && typeof value === 'number') {
        let clamped = value;
        if (min !== undefined && clamped < min) clamped = min;
        if (max !== undefined && clamped > max) clamped = max;
        if (clamped !== value) {
          onChange(clamped);
        }
      }
      onBlur?.(e);
    },
    [value, min, max, onChange, onBlur]
  );

  /**
   * Select all text on focus for fast editing on mobile.
   * Replaces the global handler in App.tsx for type="number".
   */
  const handleFocus = useCallback(
    (e: React.FocusEvent<HTMLInputElement>) => {
      // requestAnimationFrame ensures selection happens after browser's
      // default focus handling (needed for iOS Safari)
      requestAnimationFrame(() => e.target.select());
    },
    []
  );

  return (
    <input
      ref={inputRef}
      type="text"
      inputMode={decimal ? 'decimal' : 'numeric'}
      pattern={decimal ? '[0-9]*[.,]?[0-9]*' : '[0-9]*'}
      autoComplete="off"
      className={cn('input input-bordered w-full', className)}
      value={displayValue}
      onChange={handleChange}
      onBlur={handleBlur}
      onFocus={handleFocus}
      {...props}
    />
  );
}
