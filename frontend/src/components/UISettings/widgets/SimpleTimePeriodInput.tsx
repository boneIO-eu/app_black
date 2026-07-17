import React from 'react';
import { NumericInput } from '@/components/ui/NumericInput';

// TimePeriod object from backend
interface TimePeriodObject {
  milliseconds?: number;
  seconds?: number;
  minutes?: number;
  hours?: number;
  _timedelta?: number;
  _total_in_seconds?: number;
}

interface SimpleTimePeriodInputProps {
  value: string | number | TimePeriodObject;  // Accept string "30s", number (ms), or TimePeriod object
  onChange: (value: string) => void;  // Always output string like "30s"
  label: string;
  required?: boolean;
  minimum?: number;  // Minimum in milliseconds (for validation display)
  maximum?: number;  // Maximum in milliseconds (for validation and clamping)
  allowedUnits?: ('ms' | 's' | 'min' | 'h')[];  // Restrict available units
  unitlessNumberUnit?: 'ms' | 's' | 'min' | 'h';  // How to interpret unitless string values like "5"
}

/**
 * Simple time period input that outputs string values like "30s", "1000ms"
 * Backend expects string with unit, not raw milliseconds.
 *
 * Uses a native <select> for the unit picker to avoid Radix UI Select
 * compose-refs conflicts when rendered inside a Radix Dialog.
 */
const SimpleTimePeriodInput: React.FC<SimpleTimePeriodInputProps> = ({
  value,
  onChange,
  label,
  required = false,
  minimum = 0,
  maximum,
  allowedUnits = ['ms', 's', 'min', 'h'],
  unitlessNumberUnit = 'ms'
}) => {
  // Convert milliseconds to best unit
  const parseMilliseconds = (ms: number): { value: number; unit: string } => {
    if (!ms) return { value: 0, unit: 's' };
    if (ms >= 3600000 && ms % 3600000 === 0) {
      return { value: ms / 3600000, unit: 'h' };
    } else if (ms >= 60000 && ms % 60000 === 0) {
      return { value: ms / 60000, unit: 'min' };
    } else if (ms >= 1000 && ms % 1000 === 0) {
      return { value: ms / 1000, unit: 's' };
    }
    return { value: ms, unit: 'ms' };
  };

  // Parse value - can be string "30s", number (ms), or TimePeriod object from backend
  const parseValue = (val: string | number | TimePeriodObject): { value: number; unit: string } => {
    if (!val && val !== 0) return { value: 0, unit: 's' };

    // If string with unit like "30s", "1000ms", "5min"
    if (typeof val === 'string') {
      const match = val.match(/^(\d+(?:\.\d+)?)\s*(ms|s|sec|min|h|hours?)$/i);
      if (match) {
        const num = parseFloat(match[1]);
        let unit = match[2].toLowerCase();
        // Normalize units
        if (unit === 'sec') unit = 's';
        if (unit === 'hour' || unit === 'hours') unit = 'h';
        return { value: num, unit };
      }
      // Try parsing as number
      const num = parseFloat(val);
      if (!isNaN(num)) {
        if (unitlessNumberUnit === 'ms') {
          return parseMilliseconds(num);
        }
        return { value: num, unit: unitlessNumberUnit };
      }
      return { value: 0, unit: 's' };
    }

    // If number, treat as milliseconds
    if (typeof val === 'number') {
      return parseMilliseconds(val);
    }

    // If TimePeriod object from backend
    if (typeof val === 'object' && val !== null) {
      // Try to extract value in order of preference: hours > minutes > seconds > milliseconds
      if (val.hours !== undefined && val.hours > 0) {
        return { value: val.hours, unit: 'h' };
      }
      if (val.minutes !== undefined && val.minutes > 0) {
        return { value: val.minutes, unit: 'min' };
      }
      if (val.seconds !== undefined && val.seconds > 0) {
        return { value: val.seconds, unit: 's' };
      }
      if (val.milliseconds !== undefined && val.milliseconds > 0) {
        return { value: val.milliseconds, unit: 'ms' };
      }
      // Fallback: use _total_in_seconds if available
      if (val._total_in_seconds !== undefined) {
        const totalMs = val._total_in_seconds * 1000;
        return parseMilliseconds(totalMs);
      }
      return { value: 0, unit: 's' };
    }

    return { value: 0, unit: 's' };
  };

  // Convert value + unit to string like "30s"
  const toTimeString = (val: number, unit: string): string => {
    if (!val && val !== 0) return '';
    return `${val}${unit}`;
  };

  const { value: numValue, unit } = parseValue(value);
  const [inputValue, setInputValue] = React.useState(numValue);
  const [inputUnit, setInputUnit] = React.useState(unit);

  // Serialize value to a stable string so the effect doesn't fire
  // on every render when value is an object with a new reference.
  const serializedValue = React.useMemo(() => {
    if (typeof value === 'object' && value !== null) {
      return JSON.stringify(value);
    }
    return String(value ?? '');
  }, [value]);

  // Update local state when the external (serialized) value changes
  React.useEffect(() => {
    const parsed = parseValue(value);
    setInputValue(parsed.value);
    setInputUnit(parsed.unit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serializedValue]);

  const handleValueChange = (newValue: string) => {
    let num = parseFloat(newValue) || 0;

    // Clamp to maximum if set
    if (maximum !== undefined) {
      const maxForUnit = getMaxForUnit(inputUnit);
      if (num > maxForUnit) {
        num = maxForUnit;
      }
    }

    setInputValue(num);
    onChange(toTimeString(num, inputUnit));
  };

  const handleUnitChange = (newUnit: string) => {
    setInputUnit(newUnit);
    onChange(toTimeString(inputValue, newUnit));
  };

  // Get minimum value based on minimum prop (in ms)
  const getMinForUnit = (u: string): number => {
    const divisor = u === 'h' ? 3600000 : u === 'min' ? 60000 : u === 's' ? 1000 : 1;
    return Math.ceil(minimum / divisor);
  };

  // Get maximum value based on maximum prop (in ms)
  const getMaxForUnit = (u: string): number => {
    if (maximum === undefined) return Infinity;
    const divisor = u === 'h' ? 3600000 : u === 'min' ? 60000 : u === 's' ? 1000 : 1;
    return Math.floor(maximum / divisor);
  };

  const minValue = getMinForUnit(inputUnit);
  const maxValue = maximum !== undefined ? getMaxForUnit(inputUnit) : undefined;

  return (
    <div className="form-control w-full">
      <label className="label">
        <span className="label-text font-medium">
          {label}
          {required && <span className="text-error ml-1">*</span>}
        </span>
      </label>
      <div className="flex gap-2 w-full">
        <NumericInput
          value={inputValue}
          onChange={(v) => handleValueChange(String(v === '' ? 0 : v))}
          min={minValue}
          max={maxValue}
          className="flex-1 w-3/4 min-h-12"
          placeholder="0"
        />
        <div className="join border border-base-300 rounded-lg overflow-hidden shrink-0">
          {allowedUnits.map((u) => {
            const isSelected = inputUnit === u;
            return (
              <button
                key={u}
                type="button"
                onClick={() => handleUnitChange(u)}
                className={`btn btn-sm min-h-12 h-12 rounded-none border-0 join-item px-3 font-medium transition-all ${
                  isSelected 
                    ? 'btn-primary' 
                    : 'bg-base-100 hover:bg-base-200/50 text-base-content/70'
                }`}
              >
                {u}
              </button>
            );
          })}
        </div>
      </div>
      {(minimum > 0 || maximum !== undefined) && (
        <label className="label">
          <span className="label-text-alt text-base-content/70">
            {minimum > 0 && `Min: ${minimum}ms`}
            {minimum > 0 && maximum !== undefined && ' | '}
            {maximum !== undefined && `Max: ${maximum}ms`}
          </span>
        </label>
      )}
    </div>
  );
};

export default SimpleTimePeriodInput;
