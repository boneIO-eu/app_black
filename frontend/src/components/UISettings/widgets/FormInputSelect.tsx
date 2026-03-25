import React from 'react';
import HelpLabel from '../components/HelpLabel';

interface SelectOption {
  value: string | number;
  label: string;
}

interface FormInputSelectProps {
  label: string;
  value: string | number;
  options: SelectOption[];
  onChange: (value: string | number) => void;
  placeholder?: string;
  help?: string;
  required?: boolean;
}

/**
 * Reusable select dropdown form control with label and help text.
 */
export const FormInputSelect: React.FC<FormInputSelectProps> = ({
  label,
  value,
  options,
  onChange,
  placeholder,
  help,
  required,
}) => {
  const stringValue = String(value);
  
  return (
    <div className="form-control">
      <label className="label">
        <span className="label-text font-medium">
          {label}
          {required && <span className="text-error">*</span>}
        </span>
      </label>
      <select
        className="select select-bordered w-full"
        value={stringValue}
        onChange={(e) => {
          const selected = options.find(o => String(o.value) === e.target.value);
          onChange(selected?.value ?? e.target.value);
        }}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={String(opt.value)}>
            {opt.label}
          </option>
        ))}
      </select>
      {help && <HelpLabel>{help}</HelpLabel>}
    </div>
  );
};
