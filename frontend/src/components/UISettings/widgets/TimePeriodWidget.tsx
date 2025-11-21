import React from 'react';
import { WidgetProps } from '@rjsf/utils';

/**
 * Custom widget for timeperiod fields
 * Displays time with unit selector (ms, s, min, h)
 */
const TimePeriodWidget: React.FC<WidgetProps> = (props) => {
  const { value, onChange, label, required, schema } = props;

  // Parse current value (in milliseconds) to value + unit
  const parseValue = (ms: number | string | undefined): { value: number; unit: string } => {
    if (!ms) return { value: 0, unit: 's' };
    
    const msNum = typeof ms === 'string' ? parseFloat(ms) : ms;
    
    // Determine best unit
    if (msNum >= 3600000 && msNum % 3600000 === 0) {
      return { value: msNum / 3600000, unit: 'h' };
    } else if (msNum >= 60000 && msNum % 60000 === 0) {
      return { value: msNum / 60000, unit: 'min' };
    } else if (msNum >= 1000 && msNum % 1000 === 0) {
      return { value: msNum / 1000, unit: 's' };
    }
    return { value: msNum, unit: 'ms' };
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

  // Get minimum value based on schema
  const minMs = (schema as any)?.minimum || 1000; // Default minimum 1 second
  const getMinForUnit = (unit: string): number => {
    const divisor = unit === 'h' ? 3600000 : unit === 'min' ? 60000 : unit === 's' ? 1000 : 1;
    return Math.ceil(minMs / divisor);
  };
  const minValue = getMinForUnit(inputUnit);

  return (
    <div className="form-control w-full">
      <label className="label">
        <span className="label-text">
          {label || 'Time Period'}
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
      <label className="label">
        <span className="label-text-alt text-base-content/70">
          Minimum: {minValue} {inputUnit} ({minMs}ms)
        </span>
      </label>
    </div>
  );
};

export default TimePeriodWidget;
