import React from 'react';
import {
  FaInfoCircle,
  FaExclamationTriangle,
  FaCheckCircle,
  FaTimesCircle,
} from 'react-icons/fa';

export interface NoticeCalloutProps {
  /** Alert severity variant */
  variant?: 'info' | 'warning' | 'error' | 'success';
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
 * Modern notification callout with subtle transparency and border.
 * Replaces high-contrast solid alert blocks.
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
      container: 'bg-info/10 border-info/30 text-base-content',
      iconColor: 'text-info',
      defaultIcon: <FaInfoCircle />,
    },
    warning: {
      container: 'bg-warning/10 border-warning/30 text-base-content',
      iconColor: 'text-warning',
      defaultIcon: <FaExclamationTriangle />,
    },
    error: {
      container: 'bg-error/10 border-error/30 text-base-content',
      iconColor: 'text-error',
      defaultIcon: <FaTimesCircle />,
    },
    success: {
      container: 'bg-success/10 border-success/30 text-base-content',
      iconColor: 'text-success',
      defaultIcon: <FaCheckCircle />,
    },
  }[variant];

  return (
    <div
      className={`flex items-start gap-3 p-3.5 sm:p-4 rounded-xl border text-sm transition-all ${styles.container} ${className}`}
    >
      <div className={`shrink-0 mt-0.5 text-base ${styles.iconColor}`}>
        {icon || styles.defaultIcon}
      </div>
      <div className="flex-1 min-w-0">
        {title && (
          <div className="font-semibold text-sm mb-0.5 text-base-content">
            {title}
          </div>
        )}
        <div className="text-xs sm:text-sm text-base-content/80 leading-relaxed">
          {message}
        </div>
      </div>
      {action && <div className="shrink-0 ml-2">{action}</div>}
    </div>
  );
};

export default NoticeCallout;
