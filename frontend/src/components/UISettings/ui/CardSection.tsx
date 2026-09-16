import React from 'react';
import { cn } from '@/lib/utils';

export interface CardSectionProps {
  /** Small heading for the group of controls below it */
  title?: React.ReactNode;
  /** One line of context under the heading */
  description?: React.ReactNode;
  /** Optional right-aligned control for the group */
  action?: React.ReactNode;
  /** Draw a hairline above the group — for the 2nd and later groups in a card */
  divided?: boolean;
  className?: string;
  children?: React.ReactNode;
}

/**
 * A labelled group of controls inside a card, for pages where one card holds
 * several distinct things (backup: create, restore, schedule) and splitting
 * them into separate cards would bury the relationship between them.
 */
export const CardSection: React.FC<CardSectionProps> = ({
  title,
  description,
  action,
  divided = false,
  className = '',
  children,
}) => {
  return (
    <section className={cn(divided && 'pt-5 mt-5 border-t border-base-content/8', className)}>
      {(title || action) && (
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            {title && (
              <h4 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-base-content/50">
                {title}
              </h4>
            )}
            {description && (
              <p className="text-[13px] text-base-content/60 mt-1 leading-relaxed">
                {description}
              </p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
};

export default CardSection;
