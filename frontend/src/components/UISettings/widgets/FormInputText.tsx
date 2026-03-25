import React from 'react';
import HelpLabel from '../components/HelpLabel';

interface FormInputTextProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  help?: string;
  required?: boolean;
  type?: 'text' | 'password';
  maxLength?: number;
  disabled?: boolean;
}

/**
 * Reusable text input form control with label and help text.
 */
export const FormInputText: React.FC<FormInputTextProps> = ({
  label,
  value,
  onChange,
  placeholder,
  help,
  required,
  type = 'text',
  maxLength,
  disabled,
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
        type={type}
        className="input input-bordered w-full"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
        disabled={disabled}
      />
      {help && <HelpLabel>{help}</HelpLabel>}
    </div>
  );
};
