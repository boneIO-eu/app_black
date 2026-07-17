import React, { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Shared range slider component used by EntityCard (duration/brightness)
 * and CoverItem (position/tilt).
 *
 * Provides debounced onChange, local state for responsive UI,
 * smooth animated transitions for server-driven value updates,
 * optional label/icon, and consistent DaisyUI styling.
 */

export type RangeVariant = 'primary' | 'warning' | 'accent' | 'secondary' | 'info';
export type RangeSize = 'xs' | 'sm' | 'md';

interface RangeSliderProps {
  /** Current value from server/parent state */
  value: number;
  /** Minimum value */
  min: number;
  /** Maximum value */
  max: number;
  /** Step increment (default 1) */
  step?: number;
  /** Called with new value after debounce */
  onChange: (value: number) => void;
  /** Debounce delay in ms (default 300) */
  debounceMs?: number;
  /** Disable the slider */
  disabled?: boolean;
  /** DaisyUI color variant */
  variant?: RangeVariant;
  /** DaisyUI size */
  size?: RangeSize;
  /** Icon element to show before the label */
  icon?: React.ReactNode;
  /** Format the current value for display (receives local value) */
  formatValue?: (value: number) => string;
  /** Show min/max labels at edges */
  showEdgeLabels?: boolean;
  /** Min edge label (default: min value) */
  minLabel?: string;
  /** Max edge label (default: max value) */
  maxLabel?: string;
  /** Extra className for the outer wrapper */
  className?: string;
  /** Whether to wrap in a styled container (bg-secondary rounded) */
  withContainer?: boolean;
  /** Custom inline style for the input */
  inputStyle?: React.CSSProperties;
}

const VARIANT_CLASSES: Record<RangeVariant, string> = {
  primary: 'range-primary',
  warning: 'range-warning',
  accent: 'range-accent',
  secondary: 'range-secondary',
  info: 'range-info',
};

const SIZE_CLASSES: Record<RangeSize, string> = {
  xs: 'range-xs',
  sm: 'range-sm',
  md: '',
};

/** Duration of the smooth animation in ms */
const ANIMATE_DURATION_MS = 250;

const RangeSlider: React.FC<RangeSliderProps> = ({
  value,
  min,
  max,
  step = 1,
  onChange,
  debounceMs = 300,
  disabled = false,
  variant = 'primary',
  size = 'xs',
  icon,
  formatValue,
  showEdgeLabels = false,
  minLabel,
  maxLabel,
  className = '',
  withContainer = false,
  inputStyle,
}) => {
  const [localValue, setLocalValue] = useState(value);
  const [isActive, setIsActive] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cooldownRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const animFrameRef = useRef<number | null>(null);

  // Animate from current localValue to new server value when not active
  useEffect(() => {
    if (isActive) return;

    // Cancel any running animation
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }

    setLocalValue((prev) => {
      if (prev === value) return prev;

      const startValue = prev;
      const delta = value - startValue;

      // Skip animation for very small changes or first render
      if (Math.abs(delta) <= 1) return value;

      const startTime = performance.now();

      const tick = (now: number) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / ANIMATE_DURATION_MS, 1);
        // ease-out cubic for natural deceleration feel
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(startValue + delta * eased);

        setLocalValue(current);

        if (progress < 1) {
          animFrameRef.current = requestAnimationFrame(tick);
        } else {
          animFrameRef.current = null;
        }
      };

      animFrameRef.current = requestAnimationFrame(tick);
      return prev; // Don't update yet — animation will do it
    });
  }, [value, isActive]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = parseInt(e.target.value, 10);
      setLocalValue(newValue);
      setIsActive(true);

      // Cancel any server-driven animation
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }

      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      if (cooldownRef.current) {
        clearTimeout(cooldownRef.current);
      }
      debounceRef.current = setTimeout(() => {
        onChange(newValue);
        // Keep isActive true during cooldown to ignore stale server values
        // that arrive before the device processes the new command.
        cooldownRef.current = setTimeout(() => {
          setIsActive(false);
        }, 800);
      }, debounceMs);
    },
    [onChange, debounceMs],
  );

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (cooldownRef.current) clearTimeout(cooldownRef.current);
      if (animFrameRef.current !== null) cancelAnimationFrame(animFrameRef.current);
    };
  }, []);

  const rangeClass = `range ${SIZE_CLASSES[size]} ${VARIANT_CLASSES[variant]} w-full`;

  const content = (
    <>
      {/* Label row: icon + formatted value (or edge labels) */}
      {(icon || formatValue || showEdgeLabels) && (
        <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
          {(icon || formatValue) ? (
            <div className="flex items-center gap-1.5">
              {icon}
              {formatValue && (
                <span className="font-medium">{formatValue(localValue)}</span>
              )}
            </div>
          ) : (
            <span>{minLabel ?? min}</span>
          )}
          {showEdgeLabels && (
            <>
              {isActive && formatValue && (
                <span className="font-semibold text-primary">{formatValue(localValue)}</span>
              )}
              {(icon || formatValue) ? null : <span>{maxLabel ?? max}</span>}
            </>
          )}
          {showEdgeLabels && (icon || formatValue) && (
            <span className="text-gray-400">{maxLabel ?? max}</span>
          )}
        </div>
      )}
      <input
        type="range"
        className={rangeClass}
        min={min}
        max={max}
        step={step}
        value={localValue}
        onChange={handleChange}
        disabled={disabled}
        style={inputStyle}
        onMouseDown={(e) => e.stopPropagation()}
        onTouchStart={(e) => e.stopPropagation()}
      />
    </>
  );

  if (withContainer) {
    return (
      <div className={`w-full bg-secondary p-2 rounded-lg ${className}`}>
        {content}
      </div>
    );
  }

  return <div className={`w-full mt-2 ${className}`}>{content}</div>;
};

export default RangeSlider;
