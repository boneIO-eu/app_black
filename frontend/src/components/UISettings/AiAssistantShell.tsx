import React from 'react';
import { FaCopy, FaMagic } from 'react-icons/fa';
import { useTranslation } from '@/hooks/useTranslation';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export interface AiAssistantShellProps {
  /**
   * Called when user clicks "Copy prompt". Should copy the prompt to clipboard.
   * Return true on success, false on failure.
   */
  onCopyPrompt: () => Promise<boolean>;

  /**
   * Called when user clicks "Apply" in the paste dialog.
   * Receives the pasted text. Should validate and apply the configuration.
   * Return an array of error messages (empty array = success).
   */
  onApply: (responseText: string) => string[];

  /** Content rendered inside the "Details" accordion. */
  detailsContent: React.ReactNode;

  /** Optional description text shown in the paste dialog header. */
  dialogDescription?: string;

  /** Optional placeholder for the paste textarea. */
  pastePlaceholder?: string;

  /** Message shown on successful apply. Defaults to ai_apply_success. */
  successMessage?: string;
}

/**
 * Reusable AI configuration assistant shell.
 *
 * Provides the collapsible accordion UI with copy/paste buttons,
 * a paste dialog with error display, and status alerts.
 * Domain-specific logic (prompt building, response validation/apply)
 * is delegated to consumers via callbacks.
 */
export default function AiAssistantShell({
  onCopyPrompt,
  onApply,
  detailsContent,
  dialogDescription,
  pastePlaceholder,
  successMessage,
}: AiAssistantShellProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = React.useState(false);
  const [isDialogOpen, setIsDialogOpen] = React.useState(false);
  const [responseText, setResponseText] = React.useState('');
  const [errors, setErrors] = React.useState<string[]>([]);
  const [status, setStatus] = React.useState<{ type: 'success' | 'error'; message: string } | null>(null);

  /**
   * Handles the copy prompt button click.
   */
  const handleCopyPrompt = async () => {
    const success = await onCopyPrompt();
    if (success) {
      setCopied(true);
      setStatus({ type: 'success', message: t('event_form.ai_prompt_copied') });
      setTimeout(() => setCopied(false), 2000);
    } else {
      setStatus({ type: 'error', message: t('event_form.ai_copy_failed') });
    }
  };

  /**
   * Handles paste dialog open — resets state.
   */
  const openPasteDialog = () => {
    setErrors([]);
    setStatus(null);
    setResponseText('');
    setIsDialogOpen(true);
  };

  /**
   * Validates and applies the pasted AI response.
   */
  const handleApplyResponse = () => {
    const resultErrors = onApply(responseText);

    if (resultErrors.length > 0) {
      setErrors(resultErrors);
      setStatus({ type: 'error', message: t('event_form.ai_apply_failed') });
      return;
    }

    setErrors([]);
    setResponseText('');
    setIsDialogOpen(false);
    setStatus({ type: 'success', message: successMessage || t('event_form.ai_apply_success') });
  };

  return (
    <>
      <div className="collapse collapse-arrow rounded-lg border border-base-300 bg-base-200/60">
        <input type="checkbox" />
        <div className="collapse-title min-h-0 py-3 px-3">
          <div className="font-medium flex items-center gap-2">
            <FaMagic className="text-primary" />
            {t('event_form.ai_assistant_title')}
          </div>
        </div>
        <div className="collapse-content px-3 pb-3 space-y-3">
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-outline btn-sm" onClick={handleCopyPrompt}>
              <FaCopy className="mr-2" />
              {copied ? t('event_form.ai_prompt_copied_short') : t('event_form.ai_copy_prompt')}
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={openPasteDialog}>
              <FaMagic className="mr-2" />
              {t('event_form.ai_paste_response')}
            </button>
          </div>

          <div className="text-xs opacity-70 space-y-2">
            {detailsContent}
          </div>

          {status && (
            <div className={`alert ${status.type === 'success' ? 'alert-success' : 'alert-error'} py-2`}>
              <span className="text-sm whitespace-pre-wrap">{status.message}</span>
            </div>
          )}
        </div>
      </div>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-2xl bg-base-100">
          <DialogHeader>
            <DialogTitle>{t('event_form.ai_dialog_title')}</DialogTitle>
            {dialogDescription && (
              <DialogDescription>{dialogDescription}</DialogDescription>
            )}
          </DialogHeader>

          <div className="space-y-3">
            <textarea
              className="textarea textarea-bordered min-h-64 w-full font-mono text-sm"
              value={responseText}
              onChange={(e) => setResponseText(e.target.value)}
              placeholder={pastePlaceholder || t('event_form.ai_response_placeholder')}
            />

            {errors.length > 0 && (
              <div className="alert alert-error">
                <div>
                  <div className="font-medium">{t('event_form.ai_validation_failed')}</div>
                  <ul className="mt-2 list-disc list-inside text-sm space-y-1">
                    {errors.map((error, index) => (
                      <li key={`${error}-${index}`}>{error}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setErrors([]);
                setIsDialogOpen(false);
              }}
            >
              {t('common.cancel')}
            </button>
            <button type="button" className="btn btn-primary" onClick={handleApplyResponse}>
              {t('event_form.ai_apply_response')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
