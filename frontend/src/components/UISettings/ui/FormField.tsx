import React from 'react';

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
 * Standard wrapper for form controls in Settings.
 * Provides uniform label, required asterisk, help text and error handling.
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
    <div className={`form-control w-full ${className}`}>
      {label && (
        <label className="label py-1.5 px-0">
          <span className="label-text font-medium text-sm text-base-content flex items-center gap-1">
            {label}
            {required && <span className="text-error font-bold">*</span>}
          </span>
        </label>
      )}
      {children}
      {error ? (
        <label className="label py-1 px-0 whitespace-normal">
          <span className="label-text-alt text-error text-xs font-medium">{error}</span>
        </label>
      ) : help ? (
        <label className="label py-1 px-0 whitespace-normal">
          <span className="label-text-alt text-base-content/60 text-xs">{help}</span>
        </label>
      ) : null}
    </div>
  );
};

export default FormField;
