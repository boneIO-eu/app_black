/**
 * Dialog shown when the board version has been changed and the device tree
 * overlay in /boot/uEnv.txt needs updating.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface OverlayChangeDialogProps {
  open: boolean;
  currentOverlay: string | null;
  expectedOverlay: string | null;
  newVersion: string;
  isChanging: boolean;
  changeResult: 'success' | 'error' | null;
  changeError: string | null;
  onApply: () => void;
  onDismiss: () => void;
}

/**
 * Confirmation dialog for device tree overlay changes.
 *
 * Shows a warning that changing the overlay is potentially dangerous,
 * displays current vs expected overlay, and asks for user confirmation.
 * After applying, reminds the user that a system restart is required.
 */
const OverlayChangeDialog: React.FC<OverlayChangeDialogProps> = ({
  open,
  currentOverlay,
  expectedOverlay,
  newVersion,
  isChanging,
  changeResult,
  changeError,
  onApply,
  onDismiss,
}) => {
  const { t } = useTranslation();

  if (!open) return null;

  return (
    <div className="dialog-backdrop" onClick={onDismiss}>
      <div
        className="dialog-content"
        style={{ maxWidth: 520 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-header">
          <span style={{ fontSize: '1.3em' }}>⚠️</span>
          <h3 className="dialog-title">{t('overlay.title')}</h3>
        </div>

        <div className="dialog-body" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <p style={{ color: 'var(--color-warning, #f59e0b)', fontWeight: 600 }}>
            {t('overlay.warning')}
          </p>

          <p>{t('overlay.description', { version: newVersion })}</p>

          <div style={{
            background: 'var(--color-surface, #1e293b)',
            borderRadius: 8,
            padding: '0.75rem 1rem',
            fontSize: '0.875rem',
            fontFamily: 'monospace',
          }}>
            <div style={{ marginBottom: '0.25rem' }}>
              <span style={{ opacity: 0.6 }}>{t('overlay.current')}:</span>{' '}
              <strong>{currentOverlay || '—'}</strong>
            </div>
            <div>
              <span style={{ opacity: 0.6 }}>{t('overlay.expected')}:</span>{' '}
              <strong style={{ color: 'var(--color-success, #22c55e)' }}>
                {expectedOverlay || '—'}
              </strong>
            </div>
          </div>

          <p style={{ fontSize: '0.85rem', opacity: 0.7 }}>
            {t('overlay.restart_notice')}
          </p>

          {changeResult === 'success' && (
            <p style={{ color: 'var(--color-success, #22c55e)', fontWeight: 600 }}>
              ✅ {t('overlay.success')}
            </p>
          )}

          {changeResult === 'error' && (
            <p style={{ color: 'var(--color-error, #ef4444)', fontWeight: 600 }}>
              ❌ {changeError || t('overlay.change_failed')}
            </p>
          )}
        </div>

        <div className="dialog-footer">
          <button
            className="btn btn-secondary"
            onClick={onDismiss}
            disabled={isChanging}
          >
            {t('overlay.dismiss')}
          </button>
          <button
            className="btn btn-warning"
            onClick={onApply}
            disabled={isChanging || changeResult === 'success'}
            style={{
              background: 'var(--color-warning, #f59e0b)',
              color: '#000',
              fontWeight: 600,
            }}
          >
            {isChanging ? t('overlay.changing') : t('overlay.apply')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OverlayChangeDialog;
