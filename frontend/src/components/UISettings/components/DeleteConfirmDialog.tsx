/**
 * DeleteConfirmDialog - Confirmation dialog for deleting items with affected actions.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import type { AffectedAction } from '../hooks/useItemActions';

interface DeleteConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sectionType: string;
  affectedActions: AffectedAction[];
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Dialog showing affected actions/items before confirming deletion.
 */
const DeleteConfirmDialog: React.FC<DeleteConfirmDialogProps> = ({
  open,
  onOpenChange,
  sectionType,
  affectedActions,
  onConfirm,
  onCancel,
}) => {
  const { t } = useTranslation();
  const isArea = sectionType === 'areas';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-base-100">
        <DialogHeader>
          <DialogTitle className="text-warning flex items-center gap-2">
            ⚠️ {isArea ? t('settings.area_in_use_title') : t('settings.delete_warning_title')}
          </DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <p className="mb-4">
            {isArea ? t('settings.area_in_use_message') : t('settings.delete_warning_message')}
          </p>
          <div className="bg-base-200 rounded-lg p-3 max-h-48 overflow-y-auto">
            <p className="font-medium mb-2">
              {isArea ? t('settings.items_using_area') : t('settings.affected_actions')} ({affectedActions.length}):
            </p>
            <ul className="space-y-1 text-sm">
              {affectedActions.map((action, idx) => (
                <li key={idx} className="flex items-center gap-2 flex-wrap">
                  <span className="badge badge-xs badge-outline">{action.type}</span>
                  <span className="font-medium">{action.name}</span>
                  {action.actionType && <span className="text-base-content/60">({action.actionType})</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <DialogFooter>
          <button type="button" onClick={onCancel} className="btn btn-ghost">
            {t('common.cancel')}
          </button>
          <button type="button" onClick={onConfirm} className="btn btn-error">
            {isArea ? t('settings.delete_anyway') : t('settings.delete_and_remove_actions')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DeleteConfirmDialog;
