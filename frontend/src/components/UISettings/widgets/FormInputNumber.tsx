import React from 'react';
import { FormField } from '../ui';
import { NumericInput } from '@/components/ui/NumericInput';

interface FormInputNumberProps {
  label: string;
  value: number | '';
  onChange: (value: number | '') => void;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  decimal?: boolean;
  help?: string;
  required?: boolean;
}

/**
 * Reusable number input form control with label and help text.
 * Uses NumericInput internally for better mobile UX (no spinner, no scroll-wheel changes).
 */
export const FormInputNumber: React.FC<FormInputNumberProps> = ({
  label,
  value,
  onChange,
  placeholder,
  min,
  max,
  step,
  decimal,
  help,
  required,
}) => {
  return (
    <FormField label={label} required={required} help={help}>
      <NumericInput
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        decimal={decimal}
      />
    </FormField>
  );
};

