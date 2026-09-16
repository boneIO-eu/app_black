import React from 'react';
import { FormField } from '../ui';

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
  disabled?: boolean;
  error?: string;
  actionButton?: React.ReactNode;
  footerNode?: React.ReactNode;
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
  disabled,
  error,
  actionButton,
  footerNode,
}) => {
  const stringValue = String(value);
  
  return (
    <FormField label={label} required={required} help={help} error={error}>
      <div className={actionButton ? "flex gap-2" : ""}>
        <select
          className={`select select-bordered ${actionButton ? "flex-1" : "w-full"} ${error ? 'select-error' : ''}`}
          value={stringValue}
          disabled={disabled}
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
        {actionButton}
      </div>
      {footerNode}
    </FormField>
  );
};
