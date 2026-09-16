import React from 'react';
import { FormField } from '../ui';

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
  error?: string;
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
  error,
}) => {
  return (
    <FormField label={label} required={required} help={help} error={error}>
      <input
        type={type}
        className={`input input-bordered w-full ${error ? 'input-error' : ''}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
        disabled={disabled}
      />
    </FormField>
  );
};
