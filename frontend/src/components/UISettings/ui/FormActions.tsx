import React from 'react';
import { cn } from '@/lib/utils';

export interface FormActionsProps {
  /** Secondary content on the left — a hint, a timestamp, a cancel button */
  hint?: React.ReactNode;
  /** Buttons, right-aligned on anything wider than a phone */
  children: React.ReactNode;
  /** Draw a hairline above the actions. Off inside a card footer. */
  divided?: boolean;
  className?: string;
}

/**
 * The action row that closes a form.
 *
 * Buttons go right, an explanation goes left, and on a phone the buttons go
 * full width. Previously each page decided this for itself, which is how the
 * same "save" button ended up left-aligned on one page, in a `card-actions`
 * on another and inside the field grid on a third.
 */
export const FormActions: React.FC<FormActionsProps> = ({
  hint,
  children,
  divided = false,
  className = '',
}) => {
  return (
    <div
      className={cn(
        'flex flex-col-reverse sm:flex-row sm:items-center gap-3',
        hint ? 'sm:justify-between' : 'sm:justify-end',
        divided && 'pt-4 mt-1 border-t border-base-content/8',
        className,
      )}
    >
      {hint && (
        <div className="text-xs text-base-content/55 leading-relaxed min-w-0">{hint}</div>
      )}
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center shrink-0">{children}</div>
    </div>
  );
};

export default FormActions;
