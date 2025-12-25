import React from 'react';
import { FaEdit, FaTrash } from 'react-icons/fa';

interface TableActionsProps {
  onEdit: () => void;
  onDelete: () => void;
  editTitle?: string;
  deleteTitle?: string;
}

/**
 * Shared table action buttons (Edit/Delete) for all table types.
 */
const TableActions: React.FC<TableActionsProps> = ({
  onEdit,
  onDelete,
  editTitle = 'Edit',
  deleteTitle = 'Delete',
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
