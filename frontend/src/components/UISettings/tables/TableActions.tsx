import React from 'react';
import { FaEdit, FaCopy, FaTrash, FaFileExport } from 'react-icons/fa';

interface TableActionsProps {
  onEdit: () => void;
  onDelete: () => void;
  onDuplicate?: () => void;
  onDashboard?: () => void;
  editTitle?: string;
  deleteTitle?: string;
  duplicateTitle?: string;
  dashboardTitle?: string;
}

/**
 * Shared table action buttons (Edit/Duplicate/Dashboard/Delete) for all table types.
 */
const TableActions: React.FC<TableActionsProps> = ({
  onEdit,
  onDelete,
  onDuplicate,
  onDashboard,
  editTitle = 'Edit',
  deleteTitle = 'Delete',
  duplicateTitle = 'Duplicate',
  dashboardTitle = 'HA Dashboard',
}) => {
  return (
    <div className="flex space-x-1">
      <button
        onClick={onEdit}
        className="btn btn-ghost btn-xs"
        title={editTitle}
      >
        <FaEdit />
      </button>
      {onDuplicate && (
        <button
          onClick={onDuplicate}
          className="btn btn-ghost btn-xs"
          title={duplicateTitle}
        >
          <FaCopy />
        </button>
      )}
      {onDashboard && (
        <button
          onClick={onDashboard}
          className="btn btn-ghost btn-xs text-info"
          title={dashboardTitle}
        >
          <FaFileExport />
        </button>
      )}
      <button
        onClick={onDelete}
        className="btn btn-ghost btn-xs text-error"
        title={deleteTitle}
      >
        <FaTrash />
      </button>
    </div>
  );
};

export default TableActions;
