import React from 'react';
import { cn } from '@/lib/utils';

export interface EmptyStateProps {
  /** Emoji or icon */
  icon?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Optional call to action */
  action?: React.ReactNode;
  className?: string;
}

/** "Nothing here yet" — same shape for every list in settings. */
export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className = '',
}) => {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center gap-2 rounded-xl border border-dashed border-base-content/12 px-6 py-10',
        className,
      )}
    >
      {icon && <div className="text-2xl opacity-40">{icon}</div>}
      <p className="text-sm font-medium text-base-content/80">{title}</p>
      {description && (
        <p className="text-[13px] text-base-content/55 max-w-sm leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
};

export default EmptyState;
