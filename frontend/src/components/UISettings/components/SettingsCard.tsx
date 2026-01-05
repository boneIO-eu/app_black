import React from 'react';

interface SettingsCardProps {
  /** Icon component to display in the title */
  icon?: React.ReactNode;
  /** Card title */
  title: string;
  /** Optional description below title */
  description?: string;
  /** Toggle button text when section is collapsed */
  toggleButtonText?: string;
  /** Toggle button text when section is expanded */
  toggleButtonTextExpanded?: string;
  /** Whether the expandable section is shown */
  isExpanded?: boolean;
  /** Callback when toggle button is clicked */
  onToggle?: () => void;
  /** Card content (always visible) */
  children?: React.ReactNode;
  /** Expandable content (shown only when isExpanded is true) */
  expandableContent?: React.ReactNode;
  /** Additional CSS classes for the card */
  className?: string;
}

/**
 * Reusable settings card component with consistent styling.
 * Supports optional expandable sections with toggle button.
 */
const SettingsCard: React.FC<SettingsCardProps> = ({
  icon,
  title,
  description,
  toggleButtonText,
  toggleButtonTextExpanded,
  isExpanded,
  onToggle,
  children,
  expandableContent,
  className = '',
}) => {
  return (
    <div className={`card bg-base-200 ${className}`}>
      <div className="card-body">
        <div className='flex lg:items-center justify-between flex-col lg:flex-row gap-2'>
        <h3 className="card-title">
          {icon}
          {title}
        </h3>
        
        {onToggle && toggleButtonText && (
          <button
            className="btn btn-outline btn-sm w-fit"
            onClick={onToggle}
          >
            {isExpanded ? (toggleButtonTextExpanded || toggleButtonText) : toggleButtonText}
          </button>
        )}
        </div>
        
        {description && (
          <p className="text-sm opacity-70">{description}</p>
        )}
        
        {children}
        
        {isExpanded && expandableContent && (
          <div className="mt-4">
            {expandableContent}
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsCard;
