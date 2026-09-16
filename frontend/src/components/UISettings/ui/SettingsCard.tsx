import React from 'react';
import { FaChevronDown } from 'react-icons/fa';
import { cn } from '@/lib/utils';

export type SettingsCardVariant = 'default' | 'danger' | 'accent' | 'ghost';

export interface SettingsCardProps {
  /** Card title */
  title?: React.ReactNode;
  /** Optional description displayed below the title */
  description?: React.ReactNode;
  /** Optional icon in the header — rendered inside the standard icon chip */
  icon?: React.ReactNode;
  /** Optional right-aligned action (badge, buttons, toggle) in header */
  action?: React.ReactNode;
  /** Optional footer, separated by a hairline — put primary actions here */
  footer?: React.ReactNode;
  /** Visual variant */
  variant?: SettingsCardVariant;
  /** Lift the card on hover. For cards that are themselves clickable. */
  interactive?: boolean;
  /**
   * Fold the body away behind the header.
   *
   * The header becomes a disclosure: the title area and the chevron toggle
   * `open`. Use it for lists that are long and rarely needed (release
   * history, stored backups) rather than a "show/hide" button next to a card
   * whose body is then empty — that reads as a card that failed to load.
   */
  collapsible?: boolean;
  /** Whether the collapsible body is shown. Required when `collapsible`. */
  open?: boolean;
  /** Called when the disclosure is toggled. */
  onOpenChange?: (open: boolean) => void;
  /**
   * Short meta shown next to the chevron, e.g. an item count. A plain string
   * or number is drawn as a badge; anything else is rendered as given.
   */
  summary?: React.ReactNode;
  /** Additional container classes */
  className?: string;
  /** Additional card body classes */
  bodyClassName?: string;
  /** Children content */
  children?: React.ReactNode;
}

/** Nothing worth giving a padded body to. */
function isEmpty(node: React.ReactNode): boolean {
  return node === undefined || node === null || node === false || node === '';
}

/**
 * The card every settings page is built from.
 *
 * There is exactly one surface — see `.stg-card` in index.css — and the
 * variants only change the accent, never the background. That is the whole
 * point: the old pages each picked their own (`bg-base-200/50`,
 * `bg-base-200 shadow-xl`, bare `bg-base-100`), which is why moving between
 * two settings screens felt like moving between two applications.
 */
export const SettingsCard: React.FC<SettingsCardProps> = ({
  title,
  description,
  icon,
  action,
  footer,
  variant = 'default',
  interactive = false,
  collapsible = false,
  open = false,
  onOpenChange,
  summary,
  className = '',
  bodyClassName = '',
  children,
}) => {
  const hasHeader = Boolean(title || icon || action || description || collapsible);
  const showBody = !isEmpty(children) && (!collapsible || open);
  const toggle = () => onOpenChange?.(!open);

  const heading = (
    <div className="flex items-start gap-3 min-w-0">
      {icon && (
        <div
          className={cn(
            'w-10 h-10 rounded-xl flex items-center justify-center shrink-0 text-[17px]',
            variant === 'danger' ? 'stg-chip-danger' : 'stg-chip',
          )}
        >
          {icon}
        </div>
      )}
      <div className="min-w-0 pt-0.5">
        {title && (
          <h3 className="font-semibold text-[15px] tracking-tight text-base-content leading-tight">
            {title}
          </h3>
        )}
        {description && (
          <p className="text-[13px] text-base-content/60 mt-1 leading-relaxed">
            {description}
          </p>
        )}
      </div>
    </div>
  );

  return (
    <div
      className={cn(
        variant === 'ghost'
          ? 'rounded-2xl border border-dashed border-base-content/15 bg-transparent'
          : 'stg-card overflow-hidden',
        variant === 'danger' && 'stg-card-danger',
        variant === 'accent' && 'stg-card-accent',
        interactive && 'stg-card-interactive',
        className,
      )}
    >
      {hasHeader && (
        <div
          className={cn(
            'flex flex-col gap-3 px-4 pt-4 sm:px-6 sm:pt-5 sm:flex-row sm:items-start sm:justify-between',
            // A header with nothing under it still needs a bottom edge, or the
            // card looks clipped.
            !showBody && !footer && 'pb-4 sm:pb-5',
          )}
        >
          {collapsible ? (
            <button
              type="button"
              onClick={toggle}
              aria-expanded={open}
              className="flex min-w-0 flex-1 text-left cursor-pointer"
            >
              {heading}
            </button>
          ) : (
            heading
          )}

          <div className="flex items-center gap-2 shrink-0 sm:pt-0.5">
            {action}
            {collapsible && (
              <button
                type="button"
                onClick={toggle}
                aria-expanded={open}
                className="btn btn-ghost btn-sm gap-2 font-medium"
              >
                {typeof summary === 'string' || typeof summary === 'number' ? (
                  <span className="badge badge-ghost badge-sm font-semibold">{summary}</span>
                ) : (
                  summary
                )}
                <FaChevronDown
                  className={cn(
                    'w-3 h-3 transition-transform duration-200',
                    open && 'rotate-180',
                  )}
                />
              </button>
            )}
          </div>
        </div>
      )}

      {showBody && (
        <div
          className={cn(
            'px-4 sm:px-6',
            hasHeader ? 'pt-4' : 'pt-4 sm:pt-5',
            'pb-4 sm:pb-5',
            bodyClassName,
          )}
        >
          {children}
        </div>
      )}

      {footer && (
        <div className="px-4 sm:px-6 py-3 sm:py-3.5 border-t border-base-content/8 bg-base-content/[0.02] flex flex-wrap items-center gap-3">
          {footer}
        </div>
      )}
    </div>
  );
};

export default SettingsCard;
