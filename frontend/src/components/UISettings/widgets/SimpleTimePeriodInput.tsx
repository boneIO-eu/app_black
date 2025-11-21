import React from 'react';

interface SimpleTimePeriodInputProps {
  value: number;
  onChange: (value: number) => void;
  label: string;
  required?: boolean;
  minimum?: number;
}

/**
 * Simple time period input without @rjsf dependencies
 * For use in custom forms like CoverForm
 */
const SimpleTimePeriodInput: React.FC<SimpleTimePeriodInputProps> = ({
  value,
  onChange,
  label,
  required = false,
  minimum = 0
}) => {
  // Parse current value (in milliseconds) to value + unit
  const parseValue = (ms: number): { value: number; unit: string } => {
    if (!ms) return { value: 0, unit: 's' };
    
    // Determine best unit
    if (ms >= 3600000 && ms % 3600000 === 0) {
      return { value: ms / 3600000, unit: 'h' };
    } else if (ms >= 60000 && ms % 60000 === 0) {
      return { value: ms / 60000, unit: 'min' };
    } else if (ms >= 1000 && ms % 1000 === 0) {
      return { value: ms / 1000, unit: 's' };
    }
    return { value: ms, unit: 'ms' };
  };

  // Convert value + unit to milliseconds
  const toMilliseconds = (val: number, unit: string): number => {
    switch (unit) {
      case 'h': return val * 3600000;
      case 'min': return val * 60000;
      case 's': return val * 1000;
      case 'ms': return val;
      default: return val;
    }
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
    const ms = toMilliseconds(num, inputUnit);
    onChange(ms);
  };

  const handleUnitChange = (newUnit: string) => {
    setInputUnit(newUnit);
    const ms = toMilliseconds(inputValue, newUnit);
    onChange(ms);
  };

  // Get minimum value based on minimum prop
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
      <div className="flex gap-2">
        <input
          type="number"
          value={inputValue}
          onChange={(e) => handleValueChange(e.target.value)}
          min={minValue}
          step={inputUnit === 'ms' ? 100 : 1}
          className="input  flex-1"
          placeholder="Enter value"
        />
        <select
          value={inputUnit}
          onChange={(e) => handleUnitChange(e.target.value)}
          className="select ed w-24"
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
