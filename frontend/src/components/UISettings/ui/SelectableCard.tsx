import React from 'react';
import { FaChevronDown, FaChevronRight } from 'react-icons/fa';

export interface SelectableCardProps {
  /** Whether the card is selected */
  selected: boolean;
  /** Selection toggle callback */
  onToggle: () => void;
  /** Optional icon (emoji or ReactNode) */
  icon?: React.ReactNode;
  /** Primary label */
  title: React.ReactNode;
  /** Subtitle or secondary detail */
  subtitle?: React.ReactNode;
  /** Optional badge (e.g. counts '28 / 28') */
  badge?: React.ReactNode;
  /** Disabled state */
  disabled?: boolean;
  /** Whether item has expandable content */
  expandable?: boolean;
  /** Expansion state */
  isExpanded?: boolean;
  /** Expansion toggle callback */
  onExpandToggle?: () => void;
  /** Expandable children */
  children?: React.ReactNode;
  /** Additional container classes */
  className?: string;
}

/**
 * Standard selectable list item card for wizards and configuration selectors.
 * Replaces hardcoded colored frames with a cohesive DaisyUI design.
 */
export const SelectableCard: React.FC<SelectableCardProps> = ({
  selected,
  onToggle,
  icon,
  title,
  subtitle,
  badge,
  disabled = false,
  expandable = false,
  isExpanded = false,
  onExpandToggle,
  children,
  className = '',
}) => {
  return (
    <div className={`transition-all ${className}`}>
      <div
        className={`
          flex items-center gap-3.5 p-3 sm:p-3.5 rounded-xl border transition-all select-none
          ${selected
            ? 'border-primary/50 bg-primary/5 shadow-xs ring-1 ring-primary/20'
            : 'border-base-200 bg-base-100 hover:border-base-300 hover:bg-base-200/30'}
          ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}
        `}
        onClick={() => !disabled && onToggle()}
      >
        <input
          type="checkbox"
          className="checkbox checkbox-primary checkbox-sm rounded shrink-0 pointer-events-none"
          checked={selected}
          disabled={disabled}
          readOnly
        />
        {icon && (
          <div className="w-9 h-9 rounded-lg bg-base-200/70 border border-base-200/80 flex items-center justify-center text-lg shrink-0">
            {icon}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm text-base-content">{title}</span>
            {badge}
          </div>
          {subtitle && (
            <p className="text-xs text-base-content/60 mt-0.5 truncate">{subtitle}</p>
          )}
        </div>
        {expandable && (
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-square shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              onExpandToggle?.();
            }}
          >
            {isExpanded ? (
              <FaChevronDown className="w-3 h-3 text-base-content/70" />
            ) : (
              <FaChevronRight className="w-3 h-3 text-base-content/70" />
            )}
          </button>
        )}
      </div>
      {isExpanded && children && (
        <div className="ml-6 sm:ml-10 mt-1.5 p-2 rounded-xl bg-base-200/40 border border-base-200">
          {children}
        </div>
      )}
    </div>
  );
};

export default SelectableCard;
