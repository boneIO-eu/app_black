import React from 'react';
import { cn } from '@/lib/utils';

export interface FormFieldProps {
  /** Field label */
  label?: React.ReactNode;
  /** Whether field is required */
  required?: boolean;
  /** Sub-label or help description text */
  help?: React.ReactNode;
  /** Validation error message */
  error?: React.ReactNode;
  /** Additional container classes */
  className?: string;
  /** Form control children */
  children: React.ReactNode;
}

/**
 * Label, control, help text — in that order, with the same spacing on every
 * settings page.
 *
 * Deliberately not a daisyUI `label`: those add their own vertical padding
 * and the pages that used them ended up with fields spaced differently from
 * the pages that hand-rolled a `<span>` above the input.
 */
export const FormField: React.FC<FormFieldProps> = ({
  label,
  required,
  help,
  error,
  className = '',
  children,
}) => {
  return (
    <div className={cn('form-control w-full', className)}>
      {label && (
        <div className="mb-1.5 flex items-center gap-1 text-[13px] font-medium text-base-content/85">
          {label}
          {required && <span className="text-error font-bold leading-none">*</span>}
        </div>
      )}
      {children}
      {error ? (
        <p className="mt-1.5 text-xs font-medium text-error leading-relaxed">{error}</p>
      ) : help ? (
        <p className="mt-1.5 text-xs text-base-content/55 leading-relaxed">{help}</p>
      ) : null}
    </div>
  );
};

export default FormField;
