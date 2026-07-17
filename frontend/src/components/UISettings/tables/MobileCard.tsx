import React from 'react';
import { FaEdit, FaCopy, FaTrash, FaFileExport } from 'react-icons/fa';

interface MobileCardField {
  label: string;
  value: React.ReactNode;
}

interface MobileCardProps {
  /** Primary display name */
  title: string;
  /** Optional subtitle (e.g. ID) */
  subtitle?: string;
  /** Key-value fields to display */
  fields: MobileCardField[];
  /** Edit callback */
  onEdit: () => void;
  /** Delete callback */
  onDelete: () => void;
  /** Optional duplicate callback */
  onDuplicate?: () => void;
  /** Optional dashboard generation callback */
  onDashboard?: () => void;
  /** Optional extra actions (e.g. discover button) */
  extraActions?: React.ReactNode;
  /** Optional click handler for the card body (e.g. expand) */
  onClick?: () => void;
  /** Optional children rendered below fields (e.g. expanded action details) */
  children?: React.ReactNode;
}

/**
 * Mobile card view for table rows. Shown on small screens (<640px),
 * hidden on desktop where the regular table is displayed.
 */
const MobileCard: React.FC<MobileCardProps> = ({
  title,
  subtitle,
  fields,
  onEdit,
  onDelete,
  onDuplicate,
  onDashboard,
  extraActions,
  onClick,
  children,
}) => {
  return (
    <div className={`card card-compact bg-base-200 shadow-sm ${onClick ? 'cursor-pointer' : ''}`}>
      <div className="card-body p-3">
        {/* Header: title + actions */}
        <div className="flex items-start justify-between gap-2">
          <div
            className="min-w-0 flex-1"
            onClick={onClick}
          >
            <div className="font-medium text-sm truncate">{title}</div>
            {subtitle && (
              <div className="text-xs text-base-content/60 truncate">{subtitle}</div>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {extraActions}
            <button
              onClick={onEdit}
              className="btn btn-ghost btn-sm btn-square"
              title="Edit"
            >
              <FaEdit className="w-4 h-4" />
            </button>
            {onDashboard && (
              <button
                onClick={onDashboard}
                className="btn btn-ghost btn-sm btn-square text-info"
                title="HA Dashboard"
              >
                <FaFileExport className="w-4 h-4" />
              </button>
            )}
            {onDuplicate && (
              <button
                onClick={onDuplicate}
                className="btn btn-ghost btn-sm btn-square"
                title="Duplicate"
              >
                <FaCopy className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={onDelete}
              className="btn btn-ghost btn-sm btn-square text-error"
              title="Delete"
            >
              <FaTrash className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Fields grid + expand indicator */}
        <div className={onClick ? 'cursor-pointer' : ''} onClick={onClick}>
          {fields.length > 0 && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-1 text-xs">
              {fields.map((field, idx) => (
                <div key={idx} className="flex flex-col">
                  <span className="text-base-content/50">{field.label}</span>
                  <span className="truncate">{field.value}</span>
                </div>
              ))}
            </div>
          )}

          {/* Expand indicator — visible when card is expandable */}
          {onClick && (
            <div className="flex justify-center pt-1.5 -mb-1">
              <svg
                className={`w-4 h-4 text-base-content/30 transition-transform duration-200 ${children ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          )}
        </div>

        {/* Optional expanded content */}
        {children}
      </div>
    </div>
  );
};

export default MobileCard;
