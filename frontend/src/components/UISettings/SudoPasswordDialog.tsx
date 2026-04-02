import { useState, useRef, useEffect, useCallback } from 'react';
import { FaShieldAlt, FaSpinner } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';

interface SudoPasswordDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when dialog open state changes */
  onOpenChange: (open: boolean) => void;
  /** Title shown in the dialog header */
  title: string;
  /** Description shown below the title */
  description?: string;
  /** Label for the submit button */
  submitLabel?: string;
  /** Whether the submit action is in progress */
  isSubmitting?: boolean;
  /** Error message to display */
  error?: string | null;
  /** Success message to display */
  success?: string | null;
  /** Called with the password when user submits */
  onSubmit: (password: string) => void | Promise<void>;
}

/**
 * Reusable modal dialog for collecting sudo password.
 * Used across the app wherever a sudo-requiring action needs user password input.
 * Features: password input with auto-focus, Enter to submit, loading state, error/success display.
 */
export default function SudoPasswordDialog({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  isSubmitting = false,
  error,
  success,
  onSubmit,
}: SudoPasswordDialogProps) {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset password when dialog opens
  useEffect(() => {
    if (open) {
      setPassword('');
      // Auto-focus the input after a short delay (for dialog animation)
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  const handleSubmit = useCallback(() => {
    if (!password || isSubmitting) return;
    onSubmit(password);
  }, [password, isSubmitting, onSubmit]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSubmit();
    }
  }, [handleSubmit]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-base-200">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FaShieldAlt className="text-warning" />
            {title}
          </DialogTitle>
          {description && (
            <DialogDescription>{description}</DialogDescription>
          )}
        </DialogHeader>

        <div className="py-2 space-y-3">
          <div className="form-control">
            <label className="label">
              <span className="label-text">{t('sudo_dialog.password_label')}</span>
            </label>
            <input
              ref={inputRef}
              type="password"
              className="input input-bordered w-full"
              placeholder={t('sudo_dialog.password_placeholder')}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isSubmitting}
              autoComplete="current-password"
            />
            <label className="label">
              <span className="label-text-alt opacity-60">{t('sudo_dialog.password_hint')}</span>
            </label>
          </div>

          {error && (
            <div className="alert alert-error py-2">
              <span className="text-sm">{error}</span>
            </div>
          )}

          {success && (
            <div className="alert alert-success py-2">
              <span className="text-sm">{success}</span>
            </div>
          )}
        </div>

        <DialogFooter>
          <button
            className="btn btn-ghost"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            {t('common.cancel')}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={!password || isSubmitting}
          >
            {isSubmitting && <FaSpinner className="animate-spin" />}
            {submitLabel || t('sudo_dialog.submit')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
