import React from 'react';

interface SimpleTimePeriodInputProps {
  value: string | number;  // Accept both string "30s" and number (ms) for backwards compat
  onChange: (value: string) => void;  // Always output string like "30s"
  label: string;
  required?: boolean;
  minimum?: number;  // Minimum in milliseconds (for validation display)
}

/**
 * Simple time period input that outputs string values like "30s", "1000ms"
 * Backend expects string with unit, not raw milliseconds
 */
const SimpleTimePeriodInput: React.FC<SimpleTimePeriodInputProps> = ({
  value,
  onChange,
  label,
  required = false,
  minimum = 0
}) => {
  // Parse value - can be string "30s" or number (ms for backwards compat)
  const parseValue = (val: string | number): { value: number; unit: string } => {
    if (!val) return { value: 0, unit: 's' };
    
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
        return parseMilliseconds(num);
      }
      return { value: 0, unit: 's' };
    }
    
    // If number, treat as milliseconds
    return parseMilliseconds(val);
  };
  
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

  // Convert value + unit to string like "30s"
  const toTimeString = (val: number, unit: string): string => {
    if (!val && val !== 0) return '';
    return `${val}${unit}`;
  };

  const { value: numValue, unit } = parseValue(value);
  const [inputValue, setInputValue] = React.useState(numValue);
  const [inputUnit, setInputUnit] = React.useState(unit);

  // Update when external value changes
  React.useEffect(() => {
    const parsed = parseValue(value);
    setInputValue(parsed.value);
    setInputUnit(parsed.unit);
  }, [value]);

  const handleValueChange = (newValue: string) => {
    const num = parseFloat(newValue) || 0;
    setInputValue(num);
    onChange(toTimeString(num, inputUnit));
  };

  const handleUnitChange = (newUnit: string) => {
    setInputUnit(newUnit);
    onChange(toTimeString(inputValue, newUnit));
  };

  // Get minimum value based on minimum prop (in ms)
  const getMinForUnit = (unit: string): number => {
    const divisor = unit === 'h' ? 3600000 : unit === 'min' ? 60000 : unit === 's' ? 1000 : 1;
    return Math.ceil(minimum / divisor);
  };
  const minValue = getMinForUnit(inputUnit);

  return (
    <div className="form-control w-full">
      <label className="label">
        <span className="label-text font-medium">
          {label}
          {required && <span className="text-error ml-1">*</span>}
        </span>
      </label>
      <div className="flex gap-2 w-full">
        <input
          type="number"
          value={inputValue}
          onChange={(e) => handleValueChange(e.target.value)}
          min={minValue}
          step={inputUnit === 'ms' ? 100 : 1}
          className="input input-bordered"
          placeholder="0"
        />
        <select
          value={inputUnit}
          onChange={(e) => handleUnitChange(e.target.value)}
          className="select select-bordered max-w-20"
        >
          <option value="ms">ms</option>
          <option value="s">s</option>
          <option value="min">min</option>
          <option value="h">h</option>
        </select>
      </div>
      {minimum > 0 && (
        <label className="label">
          <span className="label-text-alt text-base-content/70">
            Minimum: {minValue} {inputUnit} ({minimum}ms)
          </span>
        </label>
      )}
    </div>
  );
};

export default SimpleTimePeriodInput;
