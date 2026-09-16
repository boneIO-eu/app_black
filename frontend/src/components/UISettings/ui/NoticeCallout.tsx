import React from 'react';
import {
  FaInfoCircle,
  FaExclamationTriangle,
  FaCheckCircle,
  FaTimesCircle,
} from 'react-icons/fa';
import { cn } from '@/lib/utils';

export type NoticeVariant = 'info' | 'warning' | 'error' | 'success' | 'neutral';

export interface NoticeCalloutProps {
  /** Alert severity variant */
  variant?: NoticeVariant;
  /** Optional title */
  title?: React.ReactNode;
  /** Message content */
  message: React.ReactNode;
  /** Optional custom icon */
  icon?: React.ReactNode;
  /** Optional right-aligned action */
  action?: React.ReactNode;
  /** Additional container classes */
  className?: string;
}

/**
 * The only notice style in settings.
 *
 * Replaces daisyUI's solid `alert alert-*` blocks, which at this density read
 * as three saturated bars stacked on a white page. The tint here is 8% of the
 * semantic colour with a matching left rail, so severity is still obvious at a
 * glance without the page turning into a traffic light.
 */
export const NoticeCallout: React.FC<NoticeCalloutProps> = ({
  variant = 'info',
  title,
  message,
  icon,
  action,
  className = '',
}) => {
  const styles = {
    info: {
      container: 'bg-info/8 border-info/25 border-l-info',
      iconColor: 'text-info',
      defaultIcon: <FaInfoCircle />,
    },
    warning: {
      container: 'bg-warning/10 border-warning/30 border-l-warning',
      iconColor: 'text-warning',
      defaultIcon: <FaExclamationTriangle />,
    },
    error: {
      container: 'bg-error/8 border-error/25 border-l-error',
      iconColor: 'text-error',
      defaultIcon: <FaTimesCircle />,
    },
    success: {
      container: 'bg-success/8 border-success/25 border-l-success',
      iconColor: 'text-success',
      defaultIcon: <FaCheckCircle />,
    },
    neutral: {
      container: 'bg-base-content/4 border-base-content/10 border-l-base-content/30',
      iconColor: 'text-base-content/50',
      defaultIcon: <FaInfoCircle />,
    },
  }[variant];

  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-xl border border-l-[3px] p-3.5 text-sm',
        styles.container,
        className,
      )}
    >
      <div className={cn('shrink-0 mt-px text-[15px]', styles.iconColor)}>
        {icon || styles.defaultIcon}
      </div>
      <div className="flex-1 min-w-0">
        {title && (
          <div className="font-semibold text-[13px] mb-0.5 text-base-content">{title}</div>
        )}
        <div className="text-[13px] text-base-content/75 leading-relaxed">{message}</div>
      </div>
      {action && <div className="shrink-0 ml-1 self-center">{action}</div>}
    </div>
  );
};

export default NoticeCallout;
