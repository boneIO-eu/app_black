import React from 'react';

export interface SecurityFindingCardProps {
  /** Finding severity */
  severity: 'critical' | 'warning' | 'info';
  /** Title of the security check */
  title: React.ReactNode;
  /** Detailed description */
  detail: React.ReactNode;
  /** Technical remedy or manual instructions */
  remedy?: React.ReactNode;
  /** Localized label for severity (e.g. 'Krytyczne') */
  severityLabel: string;
  /** Fix button action */
  onFix?: () => void;
  /** Fix button label */
  fixLabel?: string;
  /** Optional icon override */
  icon?: React.ReactNode;
  /** Additional container classes */
  className?: string;
}

/**
 * Standard card for security posture findings.
 * Uses a clean base-100 card with a prominent left accent border to avoid rainbow tints.
 */
export const SecurityFindingCard: React.FC<SecurityFindingCardProps> = ({
  severity,
  title,
  detail,
  remedy,
  severityLabel,
  onFix,
  fixLabel,
  icon,
  className = '',
}) => {
  const config = {
    critical: {
      borderAccent: 'border-l-4 border-l-error',
      badgeClass: 'badge-error',
      defaultIcon: '⛔',
    },
    warning: {
      borderAccent: 'border-l-4 border-l-warning',
      badgeClass: 'badge-warning',
      defaultIcon: '⚠️',
    },
    info: {
      borderAccent: 'border-l-4 border-l-info',
      badgeClass: 'badge-info',
      defaultIcon: 'ℹ️',
    },
  }[severity];

  return (
    <div
      className={`stg-card stg-card-interactive p-4 ${config.borderAccent} ${className}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <span className="text-lg shrink-0 mt-0.5" aria-hidden="true">
            {icon || config.defaultIcon}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="font-semibold text-sm text-base-content leading-tight">
                {title}
              </h4>
              <span className={`badge ${config.badgeClass} badge-sm font-semibold`}>
                {severityLabel}
              </span>
            </div>
            <p className="text-xs sm:text-sm text-base-content/80 mt-1 leading-relaxed">
              {detail}
            </p>
          </div>
        </div>
      </div>

      {/* The remedy wraps rather than truncating. It started out holding
          one-line shell commands, where an ellipsis cost nothing; several
          remedies are sentences now, and half a sentence in a monospace box
          is worse than no remedy at all. */}
      {(onFix || remedy) && (
        <div className="mt-3 pt-3 border-t border-base-content/8 flex flex-wrap items-center justify-between gap-3">
          {remedy && (
            <code className="text-xs font-mono text-base-content/70 bg-base-content/5 px-2 py-1 rounded max-w-xl whitespace-pre-wrap break-words">
              {remedy}
            </code>
          )}
          {onFix && (
            <button
              className="btn btn-sm btn-primary ml-auto gap-1.5 font-medium"
              onClick={onFix}
            >
              {fixLabel || 'Napraw'}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default SecurityFindingCard;
