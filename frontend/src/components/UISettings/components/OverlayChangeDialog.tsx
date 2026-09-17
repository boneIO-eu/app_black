/**
 * Dialog shown when the board version has been changed and the device tree
 * overlay in /boot/uEnv.txt needs updating.
 *
 * No password field: the overlay change goes through the privileged helper,
 * which accepts only the overlay names this board ships, so the application
 * needs no write access to /boot/ and no system password.
 */
import React from 'react';
import { useTranslation } from '@/hooks/useTranslation';

interface OverlayChangeDialogProps {
  open: boolean;
  currentOverlay: string | null;
  expectedOverlay: string | null;
  newVersion: string;
  overlayAvailable: boolean;
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
 * displays current vs expected overlay,
 * and requests user confirmation. When the required overlay file is
 * not installed on the system, the Apply button is disabled and a
 * prominent error message explains the situation.
 */
const OverlayChangeDialog: React.FC<OverlayChangeDialogProps> = ({
  open,
  currentOverlay,
  expectedOverlay,
  newVersion,
  overlayAvailable,
  isChanging,
  changeResult,
  changeError,
  onApply,
  onDismiss,
}) => {
  const { t } = useTranslation();

  if (!open) return null;

  const handleApply = () => {
    onApply();
  };


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
              <strong style={{ color: overlayAvailable ? 'var(--color-success, #22c55e)' : 'var(--color-error, #ef4444)' }}>
                {expectedOverlay || '—'}
              </strong>
            </div>
          </div>

          {/* Warning when overlay file is not installed on this system */}
          {!overlayAvailable && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid var(--color-error, #ef4444)',
              borderRadius: 8,
              padding: '0.75rem 1rem',
              color: 'var(--color-error, #ef4444)',
              fontWeight: 600,
              fontSize: '0.875rem',
            }}>
              🚫 {t('overlay.not_available', { overlay: expectedOverlay || '' })}
            </div>
          )}

          {overlayAvailable && (
            <p style={{ fontSize: '0.85rem', opacity: 0.7 }}>
              {t('overlay.restart_notice')}
            </p>
          )}

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
          {overlayAvailable && (
            <button
              className="btn btn-warning"
              onClick={handleApply}
              disabled={isChanging || changeResult === 'success'}
              style={{
                background: 'var(--color-warning, #f59e0b)',
                color: '#000',
                fontWeight: 600,
              }}
            >
              {isChanging ? t('overlay.changing') : t('overlay.apply')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default OverlayChangeDialog;
