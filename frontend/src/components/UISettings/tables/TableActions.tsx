import React from 'react';
import { FaEdit, FaCopy, FaTrash, FaFileExport } from 'react-icons/fa';
import { useTranslation } from '../../../hooks/useTranslation';

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
  editTitle,
  deleteTitle,
  duplicateTitle,
  dashboardTitle,
}) => {
  const { t } = useTranslation();
  return (
    <div className="stg-row-actions flex space-x-1">
      <button
        onClick={onEdit}
        className="btn btn-ghost btn-xs"
        title={editTitle ?? t('array_table_widget.edit_item')}
      >
        <FaEdit />
      </button>
      {onDuplicate && (
        <button
          onClick={onDuplicate}
          className="btn btn-ghost btn-xs"
          title={duplicateTitle ?? t('array_table_widget.duplicate_item')}
        >
          <FaCopy />
        </button>
      )}
      {onDashboard && (
        <button
          onClick={onDashboard}
          className="btn btn-ghost btn-xs text-info"
          title={dashboardTitle ?? t('array_table_widget.ha_dashboard')}
        >
          <FaFileExport />
        </button>
      )}
      <button
        onClick={onDelete}
        className="btn btn-ghost btn-xs text-error"
        title={deleteTitle ?? t('array_table_widget.delete_item')}
      >
        <FaTrash />
      </button>
    </div>
  );
};

export default TableActions;
