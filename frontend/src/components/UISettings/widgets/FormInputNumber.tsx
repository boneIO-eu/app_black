import React from 'react';
import HelpLabel from '../components/HelpLabel';

interface FormInputNumberProps {
  label: string;
  value: number | '';
  onChange: (value: number | '') => void;
  placeholder?: string;
  min?: number;
  max?: number;
  help?: string;
  required?: boolean;
}

/**
 * Reusable number input form control with label and help text.
 */
export const FormInputNumber: React.FC<FormInputNumberProps> = ({
  label,
  value,
  onChange,
  placeholder,
  min,
  max,
  help,
  required,
}) => {
  return (
    <div className="form-control">
      <label className="label">
        <span className="label-text font-medium">
          {label}
          {required && <span className="text-error">*</span>}
        </span>
      </label>
      <input
        type="number"
        className="input input-bordered w-full"
        value={value}
        onChange={(e) => {
          const rawValue = e.target.value;
          if (rawValue === '') {
            onChange('');
            return;
          }

          const parsedValue = parseInt(rawValue, 10);
          onChange(Number.isNaN(parsedValue) ? '' : parsedValue);
        }}
        placeholder={placeholder}
        min={min}
        max={max}
      />
      {help && <HelpLabel>{help}</HelpLabel>}
    </div>
  );
};
