import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface SimpleTimePeriodInputProps {
  value: string | number;  // Accept both string "30s" and number (ms) for backwards compat
  onChange: (value: string) => void;  // Always output string like "30s"
  label: string;
  required?: boolean;
  minimum?: number;  // Minimum in milliseconds (for validation display)
  maximum?: number;  // Maximum in milliseconds (for validation and clamping)
  allowedUnits?: ('ms' | 's' | 'min' | 'h')[];  // Restrict available units
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
  minimum = 0,
  maximum,
  allowedUnits = ['ms', 's', 'min', 'h']
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
  const getMinForUnit = (unit: string): number => {
    const divisor = unit === 'h' ? 3600000 : unit === 'min' ? 60000 : unit === 's' ? 1000 : 1;
    return Math.ceil(minimum / divisor);
  };
  
  // Get maximum value based on maximum prop (in ms)
  const getMaxForUnit = (unit: string): number => {
    if (maximum === undefined) return Infinity;
    const divisor = unit === 'h' ? 3600000 : unit === 'min' ? 60000 : unit === 's' ? 1000 : 1;
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
        <input
          type="number"
          value={inputValue}
          onChange={(e) => handleValueChange(e.target.value)}
          min={minValue}
          max={maxValue}
          step={inputUnit === 'ms' ? 10 : 1}
          className="input input-bordered flex-1 min-h-12"
          placeholder="0"
        />
        <Select value={inputUnit} onValueChange={handleUnitChange}>
          <SelectTrigger className="w-20">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {allowedUnits.includes('ms') && <SelectItem value="ms">ms</SelectItem>}
            {allowedUnits.includes('s') && <SelectItem value="s">s</SelectItem>}
            {allowedUnits.includes('min') && <SelectItem value="min">min</SelectItem>}
            {allowedUnits.includes('h') && <SelectItem value="h">h</SelectItem>}
          </SelectContent>
        </Select>
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
