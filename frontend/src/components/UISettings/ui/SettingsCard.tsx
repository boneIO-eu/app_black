import React from 'react';

export interface SettingsCardProps {
  /** Card title */
  title?: React.ReactNode;
  /** Optional description displayed below the title */
  description?: React.ReactNode;
  /** Optional icon in the header */
  icon?: React.ReactNode;
  /** Optional right-aligned action (badge, buttons, toggle) in header */
  action?: React.ReactNode;
  /** Visual variant */
  variant?: 'default' | 'danger' | 'ghost';
  /** Additional container classes */
  className?: string;
  /** Additional card body classes */
  bodyClassName?: string;
  /** Children content */
  children?: React.ReactNode;
}

/**
 * Standard card container for Settings views.
 * Ensures consistent background (bg-base-100), borders, shadows, and header styling.
 */
export const SettingsCard: React.FC<SettingsCardProps> = ({
  title,
  description,
  icon,
  action,
  variant = 'default',
  className = '',
  bodyClassName = '',
  children,
}) => {
  const variantClasses = {
    default: 'bg-base-100 border border-base-200 shadow-xs',
    danger: 'bg-base-100 border border-error/30 shadow-xs',
    ghost: 'bg-transparent border border-base-200/70',
  }[variant];

  const hasHeader = Boolean(title || icon || action);

  return (
    <div className={`card ${variantClasses} rounded-2xl transition-all ${className}`}>
      <div className={`card-body p-4 sm:p-6 ${bodyClassName}`}>
        {hasHeader && (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-base-200/80 pb-3 sm:pb-4 mb-4">
            <div className="flex items-start sm:items-center gap-3 min-w-0">
              {icon && (
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                  variant === 'danger' ? 'bg-error/10 text-error' : 'bg-primary/10 text-primary'
                }`}>
                  {icon}
                </div>
              )}
              <div className="min-w-0">
                {title && (
                  <h3 className="font-semibold text-base text-base-content leading-tight">
                    {title}
                  </h3>
                )}
                {description && (
                  <p className="text-xs text-base-content/60 mt-0.5 leading-relaxed">
                    {description}
                  </p>
                )}
              </div>
            </div>
            {action && <div className="flex items-center gap-2 shrink-0">{action}</div>}
          </div>
        )}
        {children}
      </div>
    </div>
  );
};

export default SettingsCard;
