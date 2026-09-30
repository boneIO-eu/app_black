import { useState } from 'react';
import { FaUserMinus } from 'react-icons/fa';
import { useTranslation } from '../hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';

interface AccountDeleteDialogProps {
  /** The account to delete, or null when the dialog is closed. */
  username: string | null;
  onClose: () => void;
  /** Deletes the account; the dialog stays open, busy, until it settles. */
  onConfirm: (username: string) => Promise<void>;
}

/** Ask before deleting an account, in the panel's own dialog. */
export default function AccountDeleteDialog({ username, onClose, onConfirm }: AccountDeleteDialogProps) {
  const { t } = useTranslation();
  const [deleting, setDeleting] = useState(false);

  const confirm = async () => {
    if (!username) return;
    setDeleting(true);
    try {
      await onConfirm(username);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Dialog open={username !== null} onOpenChange={(next) => !next && !deleting && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <span className="stg-chip w-10 h-10 rounded-xl flex items-center justify-center shrink-0 text-error">
              <FaUserMinus />
            </span>
            <DialogTitle>{t('accounts.confirm_delete', { username: username ?? '' })}</DialogTitle>
          </div>
          <DialogDescription>{t('accounts.confirm_delete_intro')}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <button type="button" className="btn btn-ghost max-sm:btn-lg" onClick={onClose} disabled={deleting}>
            {t('common.cancel')}
          </button>
          <button type="button" className="btn btn-error max-sm:btn-lg" onClick={confirm} disabled={deleting}>
            {deleting && <span className="loading loading-spinner loading-sm" />}
            {t('accounts.delete')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
