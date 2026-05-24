import React from 'react';
import { FaEdit, FaCopy, FaTrash } from 'react-icons/fa';

interface TableActionsProps {
  onEdit: () => void;
  onDelete: () => void;
  onDuplicate?: () => void;
  editTitle?: string;
  deleteTitle?: string;
  duplicateTitle?: string;
}

/**
 * Shared table action buttons (Edit/Duplicate/Delete) for all table types.
 */
const TableActions: React.FC<TableActionsProps> = ({
  onEdit,
  onDelete,
  onDuplicate,
  editTitle = 'Edit',
  deleteTitle = 'Delete',
  duplicateTitle = 'Duplicate',
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
