/**
 * ImportDialog - Dialog for confirming YAML/JSON import with merge/replace options.
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

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  importData: any[] | null;
  importError: string | null;
  importMode: 'replace' | 'merge';
  onModeChange: (mode: 'replace' | 'merge') => void;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Dialog showing import preview with merge/replace mode selection.
 */
const ImportDialog: React.FC<ImportDialogProps> = ({
  open,
  onOpenChange,
  importData,
  importError,
  importMode,
  onModeChange,
  onConfirm,
  onCancel,
}) => {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-base-100">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            📥 {t('import_export.import_title')}
          </DialogTitle>
        </DialogHeader>
        <div className="py-4 space-y-4">
          {importError ? (
            <div className="alert alert-error">
              <span>{importError}</span>
            </div>
          ) : (
            <>
              <p>{t('import_export.import_confirm').replace('{count}', String(importData?.length || 0))}</p>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-3">
                  <input
                    type="radio"
                    name="importMode"
                    className="radio radio-primary"
                    checked={importMode === 'merge'}
                    onChange={() => onModeChange('merge')}
                  />
                  <div>
                    <span className="label-text font-medium">{t('import_export.mode_merge')}</span>
                    <p className="text-xs text-base-content/60">{t('import_export.mode_merge_desc')}</p>
                  </div>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-3">
                  <input
                    type="radio"
                    name="importMode"
                    className="radio radio-warning"
                    checked={importMode === 'replace'}
                    onChange={() => onModeChange('replace')}
                  />
                  <div>
                    <span className="label-text font-medium">{t('import_export.mode_replace')}</span>
                    <p className="text-xs text-base-content/60">{t('import_export.mode_replace_desc')}</p>
                  </div>
                </label>
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <button type="button" onClick={onCancel} className="btn btn-ghost">
            {t('common.cancel')}
          </button>
          {!importError && (
            <button
              type="button"
              onClick={onConfirm}
              className={`btn ${importMode === 'replace' ? 'btn-warning' : 'btn-primary'}`}
            >
              {t('import_export.confirm_import')}
            </button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ImportDialog;
